"""Optional HeyGen Arabic voice adapter (Fouad), keeping audio generation server-side.

Requires the LECTURE_HEYGEN_API_KEY secret; never commit keys or private PDF files.
"""
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

HEYGEN_API_URL = "https://api.heygen.com/v3/models/audio/tts"
FOUAD_VOICE_ID = "dc4ee8e4f0bc4099ad5be2a8431ca556"
MAX_AUDIO_BYTES = 100 * 1024 * 1024


def _safe_audio_url(url):
    if not isinstance(url, str):
        raise RuntimeError("HeyGen did not provide an audio URL.")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname or not (
        parsed.hostname == "heygen.ai" or parsed.hostname.endswith(".heygen.ai")
        or parsed.hostname == "heygen.com" or parsed.hostname.endswith(".heygen.com")
    ):
        raise RuntimeError("HeyGen returned an unexpected audio host.")
    return url


class HeyGenFouad:
    """Generate WAV for one Arabic paragraph; the caller handles scene timing."""

    def __init__(self, api_key=None, voice_id=FOUAD_VOICE_ID):
        self.api_key = api_key or os.environ.get("LECTURE_HEYGEN_API_KEY", "")
        if not self.api_key:
            raise RuntimeError(
                "صوت فؤاد يحتاج LECTURE_HEYGEN_API_KEY في GitHub Actions Secrets أو البيئة المحلية."
            )
        self.voice_id = voice_id

    def synthesize(self, text, target, speed=1.0):
        if not text.strip() or len(text) > 10000:
            raise ValueError("HeyGen requires 1–10,000 characters per request.")
        speed = float(speed)
        if not .75 <= speed <= 1.25:
            raise ValueError("HeyGen speed must be between 0.75 and 1.25.")
        payload = {
            "text": text, "voice_id": self.voice_id, "language": "ar",
            "model": "heygen-voice-1", "speed": speed,
            "apply_text_normalization": "on", "with_timestamps": False,
        }
        request = Request(
            HEYGEN_API_URL,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"X-Api-Key": self.api_key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=180) as response:
                result = json.load(response)
        except Exception as error:
            # Do not include potentially sensitive API responses in logs.
            raise RuntimeError(
                f"HeyGen narration failed ({type(error).__name__}); check quota, voice and secret."
            ) from None
        audio_url = _safe_audio_url((result.get("data") or {}).get("audio_url"))
        temp = Path(target).with_suffix(".download")
        try:
            with urlopen(audio_url, timeout=180) as response, temp.open("wb") as stream:
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if total > MAX_AUDIO_BYTES:
                        raise ValueError("HeyGen audio exceeded safe download limit.")
                    stream.write(chunk)
            if total < 100:
                raise ValueError("HeyGen returned an empty audio file.")
            temp.replace(target)
        finally:
            temp.unlink(missing_ok=True)
