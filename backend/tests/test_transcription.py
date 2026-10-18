from types import SimpleNamespace

from app.domain import transcription


def test_transcription_returns_output_text(monkeypatch):
    calls = []

    class FakeInteractions:
        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(output_text="I keep hitting this corner.")

    fake_client = SimpleNamespace(interactions=FakeInteractions())
    monkeypatch.setattr(transcription, "_client", lambda force_new=False: fake_client)

    result = transcription.transcribe_audio_bytes(b"abc", "audio/webm")

    assert result == "I keep hitting this corner."
    assert calls[0]["model"] == transcription.settings.gemini_transcription_model
    assert calls[0]["input"][1]["type"] == "audio"
    assert calls[0]["input"][1]["mime_type"] == "audio/webm"
    assert calls[0]["store"] is False


def test_transcription_rejects_empty_audio():
    try:
        transcription.transcribe_audio_bytes(b"", "audio/webm")
    except ValueError as exc:
        assert "empty" in str(exc).lower()
    else:
        raise AssertionError("Expected empty audio to be rejected")
