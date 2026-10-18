from __future__ import annotations

import base64
import logging
import threading
import time

from google import genai

from app.config import settings
from app.logging_config import get_logger, log_event


logger = get_logger("arthistics.transcription")

_client_instance: genai.Client | None = None
_client_lock = threading.Lock()


def _client(force_new: bool = False) -> genai.Client:
    global _client_instance
    with _client_lock:
        if force_new or _client_instance is None:
            _client_instance = genai.Client()
        return _client_instance


def transcribe_audio_bytes(data: bytes, mime_type: str) -> str:
    """Transcribe a short microphone recording with a separate Gemini request.

    This helper is intentionally outside the ADK agent loop. The returned text is
    placed in the chat composer for the user to review/edit before it is sent to
    the Arthistics agent.
    """
    if not data:
        raise ValueError("Audio recording is empty.")

    encoded = base64.b64encode(data).decode("utf-8")
    request = {
        "model": settings.gemini_transcription_model,
        "input": [
            {
                "type": "text",
                "text": (
                    "Transcribe the spoken words accurately. Preserve the language the user speaks. "
                    "Add natural punctuation, but do not translate, answer, summarize, or add commentary. "
                    "Return only the transcript."
                ),
            },
            {
                "type": "audio",
                "data": encoded,
                "mime_type": mime_type,
            },
        ],
        "store": False,
    }

    started = time.perf_counter()
    try:
        interaction = _client().interactions.create(**request)
    except RuntimeError as exc:
        if "closed" not in str(exc).lower():
            raise
        interaction = _client(force_new=True).interactions.create(**request)

    transcript = (getattr(interaction, "output_text", None) or "").strip()
    if not transcript:
        raise RuntimeError("Gemini did not return a transcript.")

    log_event(
        logger,
        logging.INFO,
        "Voice dictation transcribed",
        event_type="voice_transcription_complete",
        model=settings.gemini_transcription_model,
        duration_ms=round((time.perf_counter() - started) * 1000),
        size_bytes=len(data),
        mime_type=mime_type,
        status="success",
    )
    return transcript
