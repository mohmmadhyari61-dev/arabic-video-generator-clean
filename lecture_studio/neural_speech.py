"""CPU inference adapters. Model weights and reference recordings are fetched at runtime."""
import os
import re
import subprocess
from importlib.resources import files
from pathlib import Path
from tempfile import TemporaryDirectory

AUDAR_REPO = "audarai/Audar-TTS-V1-Flash"
AUDAR_REFERENCE = ("لا يمكنني الانتظار لأخبرك، لقد أنجزنا المشروع أخيراً بعد كلّ هذا التعب، "
                   "وصدّقني، إنه أجمل شعورٍ على الإطلاق!")
SILMA_REFERENCE = ("ويدقق النظر في القرآن الكريم وسائر الكتب السماوية ويتبع مسالك الرسل "
                   "العظام عليهم الصلاة والسلام.")
PORTABLE_ENGINES = ("silma", "audar")


def inference_threads():
    return max(1, min(4, os.cpu_count() or 1))


class Silma:
    def __init__(self):
        import torch
        from silma_tts.api import SilmaTTS

        torch.set_num_threads(inference_threads())
        self.model = SilmaTTS(device="cpu", enable_normalizer=False, force_tashkeel=False)
        self.reference = str(files("silma_tts").joinpath("infer/ref_audio_samples/ar.ref.24k.wav"))

    def synthesize(self, text, path):
        self.model.infer(ref_file=self.reference, ref_text=SILMA_REFERENCE, gen_text=text,
                         file_wave=str(path), seed=42, normalize_numbers=False,
                         force_tashkeel=False, show_info=lambda *args: None)


class Audar:
    def __init__(self):
        import soundfile
        import torch
        from huggingface_hub import hf_hub_download
        from huggingface_hub.errors import GatedRepoError
        from llama_cpp import Llama
        from neucodec import NeuCodec

        torch.set_num_threads(inference_threads())
        self.torch, self.soundfile = torch, soundfile
        try:
            self.codec = NeuCodec.from_pretrained("neuphonic/neucodec").eval()
        except GatedRepoError:
            raise RuntimeError(
                "يتطلب Audar قبول شروط NeuCodec على Hugging Face وإعداد رمز قراءة مخوّل "
                "في HF_TOKEN محلياً أو LECTURE_HF_TOKEN في GitHub Secrets."
            ) from None
        model = hf_hub_download(AUDAR_REPO, "Audar-TTS-V1-Flash-Q5_K_M.gguf")
        self.llm = Llama(model_path=model, n_ctx=4096, n_threads=inference_threads(),
                         n_gpu_layers=0, seed=42, verbose=False)
        ref = hf_hub_download(AUDAR_REPO, "samples/demo_male_1_ar.wav", revision="a26df17")
        with TemporaryDirectory() as folder:
            source = Path(folder) / "reference.wav"
            subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", ref, "-ac", "1",
                            "-ar", "16000", str(source)], check=True)
            with torch.inference_mode():
                codes = self.codec.encode_code(str(source)).flatten().tolist()
        self.prefix = (
            f"user: Convert the text to speech:<|REF_TEXT_START|>{AUDAR_REFERENCE}<|REF_TEXT_END|>"
            "<|REF_SPEECH_START|>" + "".join(f"<|speech_{i}|>" for i in codes) + "<|REF_SPEECH_END|>"
        )
        self.stop, = self.llm.tokenize(b"<|TARGET_CODES_END|>", add_bos=False, special=True)

    def synthesize(self, text, path):
        # Escape Audar control-token delimiters from arbitrary lecture text.
        text = text.replace("<|", "‹|").replace("|>", "|›")
        prompt = self.prefix + f"<|TARGET_TEXT_START|>{text}<|TARGET_TEXT_END|>\nassistant:<|TARGET_CODES_START|>"
        tokens = self.llm.tokenize(prompt.encode(), add_bos=False, special=True)
        generated = []
        for token in self.llm.generate(tokens, temp=.65, top_k=40, top_p=.9, repeat_penalty=1.1):
            if token == self.stop:
                break
            if len(generated) == 2048:
                raise RuntimeError("Audar exceeded its speech token budget for this passage.")
            generated.append(token)
        result = self.llm.detokenize(generated, special=True).decode("utf-8")
        codes = [int(code) for code in re.findall(r"<\|speech_(\d+)\|>", result)]
        if len(codes) < 10:
            raise RuntimeError("Audar returned no usable speech tokens.")
        with self.torch.inference_mode():
            wav = self.codec.decode_code(self.torch.tensor(codes)[None, None, :])
        self.soundfile.write(path, wav[0, 0].cpu().numpy(), 24000)
