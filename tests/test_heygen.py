import io
import json
from urllib.error import HTTPError

import pytest

from lecture_studio.heygen_voice import HeyGenFouad, _safe_audio_url


def test_refuses_missing_secret(monkeypatch):
    monkeypatch.delenv("LECTURE_HEYGEN_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="LECTURE_HEYGEN_API_KEY"):
        HeyGenFouad()


@pytest.mark.parametrize("url", [
    "http://resource2.heygen.ai/x.wav",
    "https://resource2.heygen.ai.evil.org/x.wav",
    "https://untrusted.example/audio.wav",
    "file:///etc/passwd",
])
def test_restricts_audio_hosts(url):
    with pytest.raises(RuntimeError, match="unexpected audio host"):
        _safe_audio_url(url)


class FakeResponse:
    def __init__(self, data):
        self.stream = io.BytesIO(data)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.stream.close()

    def read(self, n=-1):
        return self.stream.read(n)


def test_generates_arabic_fouad_audio_without_leaking_key(tmp_path, monkeypatch):
    calls = []

    def fake_open(request, timeout=180):
        calls.append(request)
        if len(calls) == 1:
            payload = json.loads(request.data.decode("utf-8"))
            assert payload["voice_id"] == "dc4ee8e4f0bc4099ad5be2a8431ca556"
            assert payload["language"] == "ar"
            assert payload["text"] == "الذِّمَّة المالية"
            assert payload["apply_text_normalization"] == "on"
            assert payload["speed"] == 1.0
            assert request.get_header("X-api-key") == "test-secret"
            return FakeResponse(json.dumps({
                "data": {"audio_url": "https://resource2.heygen.ai/fouad.wav"}
            }).encode())
        return FakeResponse(b"RIFF" + b"\0" * 256)

    monkeypatch.setattr("lecture_studio.heygen_voice.urlopen", fake_open)
    path = tmp_path / "narration.wav"
    HeyGenFouad(api_key="test-secret").synthesize("الذِّمَّة المالية", path)
    assert path.read_bytes().startswith(b"RIFF")
    assert not (tmp_path / "narration.download").exists()


def test_rejects_invalid_speed_without_request(tmp_path):
    with pytest.raises(ValueError, match="speed"):
        HeyGenFouad(api_key="x").synthesize("نص", tmp_path / "a.wav", speed=2)


def test_sanitizes_service_failure(tmp_path, monkeypatch):
    def fake_open(*args, **kwargs):
        raise HTTPError("https://api.heygen.com/v3/models/audio/tts",
                        401, "private-token-secret", {}, None)

    monkeypatch.setattr("lecture_studio.heygen_voice.urlopen", fake_open)
    with pytest.raises(RuntimeError) as err:
        HeyGenFouad(api_key="private-token-secret").synthesize(
            "الذِّمَّة", tmp_path / "a.wav"
        )
    assert "private-token-secret" not in str(err.value)
