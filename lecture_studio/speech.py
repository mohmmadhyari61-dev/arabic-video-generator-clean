import asyncio
import os
import subprocess
import time
from pathlib import Path

from .neural_speech import Audar, PORTABLE_ENGINES, Silma
from .pronunciation import chunks, spoken_text



class Speaker:
    def __init__(self, backend, voice, rate):
        self.backend, self.voice, self.rate = backend, voice, rate
        self.engine = None

    @property
    def suffix(self):
        return ".mp3" if self.backend == "edge" else ".wav"

    def chunks(self, text):
        if self.backend == "silma":
            # Keep each request below SILMA's internal limit after vocalization
            # so its parallel batch path is never needed for ordinary sentences.
            return chunks(text, 110, lambda part: len(spoken_text(part)))
        return chunks(text, 175 if self.backend == "audar" else 240)

    def speak(self, text, path):
        temporary = path.with_name("temporary" + path.suffix)
        raw = path.with_name("raw-narration.wav")
        text = spoken_text(text)
        rate = 1 + int(self.rate.rstrip("%")) / 100
        try:
            if self.backend in PORTABLE_ENGINES:
                if self.engine is None:
                    self.engine = (Silma if self.backend == "silma" else Audar)()
                self.engine.synthesize(text, raw)
                subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(raw),
                                "-af", f"atempo={rate:.2f}", "-ar", "24000", "-ac", "1",
                                str(temporary)], check=True)
            elif self.backend == "piper":
                if self.engine is None:
                    from piper import PiperVoice
                    self.engine = PiperVoice.load(os.environ["PIPER_MODEL"])
                import wave
                from piper import SynthesisConfig
                with wave.open(str(temporary), "wb") as stream:
                    self.engine.synthesize_wav(text, stream, syn_config=SynthesisConfig(
                        length_scale=1 / rate))
            elif self.backend == "espeak":
                subprocess.run(["espeak-ng", "-v", "ar", "-s",
                                str(round(155 * rate)),
                                "--stdin", "-w", str(temporary)], input=text.encode(), check=True)
            else:
                import edge_tts
                proxy = os.environ.get("HTTPS_PROXY") or None
                for delay in (0, 2, 5):
                    time.sleep(delay)
                    try:
                        asyncio.run(edge_tts.Communicate(text, self.voice, rate=self.rate,
                                                        proxy=proxy).save(str(temporary)))
                        break
                    except Exception as exc:
                        if delay == 5:
                            raise RuntimeError(f"تعذر توليد الصوت عبر Edge ({type(exc).__name__}).") from None
            if duration(temporary) < .1:
                raise ValueError("مقطع الصوت الناتج فارغ.")
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)
            raw.unlink(missing_ok=True)


def duration(path: Path):
    return float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)], text=True).strip())
