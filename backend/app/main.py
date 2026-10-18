from __future__ import annotations

import asyncio
import logging
import mimetypes
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from google.genai import types

from app.config import settings
from app.logging_config import configure_logging, get_logger, log_event
from app.support_booking import booking_context, create_booking, get_available_slots
from app.outcomes import record_outcome
from app.models import (
    AnalyzeRequest,
    ArtifactRef,
    ChatRequest,
    RefineRequest,
    SessionCreateRequest,
    SessionResponse,
    UploadResponse,
    SupportBookingRequest,
    SupportBookingResponse,
    TranscriptionResponse,
    OutcomeFeedbackRequest,
    OutcomeFeedbackResponse,
)
from app.services import runtime
from app.streaming import stream_agent_run
from app.static_ui import mount_landing_site, mount_local_ui
from app.domain.measurement_core import generate_calibration_marker_svg
from app.domain.identity import new_session_id, new_user_id
from app.domain.transcription import transcribe_audio_bytes
from app.domain.memory_policy import outcome_memory_fact
from app.memory_writer import write_direct_memory


configure_logging(settings.arthistics_log_level, settings.arthistics_log_format)
logger = get_logger("arthistics.api")

# Fast ownership cache for the current Cloud Run instance.
# It avoids an unnecessary managed Vertex session round trip when the browser
# fetches an artifact that was generated in the same active session.
# If the instance restarts or the session is not cached, endpoints fall back
# to the authoritative session service check.
_SESSION_OWNER_CACHE: dict[str, str] = {}

APP_VERSION = "0.13.2"


IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
VIDEO_MIME_TYPES = {"video/mp4", "video/webm", "video/quicktime"}
AUDIO_MIME_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/mp4",
    "audio/webm",
    "audio/ogg",
    "audio/aac",
}
MIME_EXTENSION = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mp4": ".m4a",
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/aac": ".aac",
}


@asynccontextmanager
async def lifespan(_: FastAPI):
    await runtime.start()
    try:
        yield
    finally:
        await runtime.stop()


app = FastAPI(
    title="Iyal.ai API",
    version=APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

mount_local_ui(app)


async def require_session(user_id: str, session_id: str):
    service = runtime.require_session_service()
    session = await service.get_session(
        app_name=settings.app_name,
        user_id=user_id,
        session_id=session_id,
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    _SESSION_OWNER_CACHE[session_id] = user_id
    return session


async def require_artifact_session(user_id: str, session_id: str) -> None:
    """Authorize artifact reads without repeating a managed-session lookup.

    Sessions created or already verified on this instance are cached by owner.
    A cache miss still uses the authoritative session service, so restarts and
    older sessions remain supported.
    """
    cached_owner = _SESSION_OWNER_CACHE.get(session_id)
    if cached_owner == user_id:
        return
    if cached_owner is not None and cached_owner != user_id:
        raise HTTPException(status_code=404, detail="Session not found.")
    await require_session(user_id, session_id)


async def root() -> dict:
    # Registered at "/" only when the landing site is absent (see end of module).
    return {"service": "arthistics-backend", "status": "ok", "version": APP_VERSION}


@app.get("/api/calibration/marker.svg")
async def calibration_marker() -> Response:
    svg = generate_calibration_marker_svg()
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={
            "Content-Disposition": 'inline; filename="iyal-calibration-marker.svg"',
            "Cache-Control": "public, max-age=3600",
        },
    )


@app.get("/api/calibration/info")
async def calibration_info() -> dict:
    return {
        "primary_reference": {
            "type": "a4",
            "size_mm": [settings.a4_short_side_mm, settings.a4_long_side_mm],
            "requires_printing": False,
            "instructions": [
                "Place the complete target region on a plain A4 sheet.",
                "Keep all four A4 corners visible.",
                "Take the photo roughly perpendicular to the sheet.",
                "Use the calibrated top photo only for dimensions that are naturally visible from above.",
                "For thickness/depth, prefer a simple ruler or caliper measurement instead of an awkward object pose.",
            ],
        },
        "fallback_reference": {
            "type": "aruco",
            "dictionary": settings.calibration_marker_dictionary,
            "marker_id": settings.calibration_marker_id,
            "marker_size_mm": settings.calibration_marker_size_mm,
            "marker_uri": "/api/calibration/marker.svg",
        },
    }


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "version": APP_VERSION,
        "model": settings.gemini_model,
        "location": settings.google_cloud_location,
        "artifact_store": "gcs",
        "session_store": (
            "vertex" if settings.managed_sessions_enabled
            else "database" if settings.session_db_url
            else "memory"
        ),
        "memory_bank": "configured" if settings.managed_memory_enabled else "disabled",
        "product_search": "enabled" if settings.product_search_enabled else "disabled",
    }


@app.post("/api/sessions", response_model=SessionResponse)
async def create_session(request: SessionCreateRequest) -> SessionResponse:
    user_id = request.user_id or new_user_id()
    session_id = new_session_id()
    service = runtime.require_session_service()
    session = await service.create_session(
        app_name=settings.app_name,
        user_id=user_id,
        session_id=session_id,
        state={
            "current_design_version": 0,
            "prototype_scope": "grip_sleeve_v1",
            "conversation_mode": True,
        },
    )
    _SESSION_OWNER_CACHE[session.id] = user_id
    log_event(
        logger,
        logging.INFO,
        "Conversation session created",
        event_type="session_created",
        session_id=session.id,
        status="success",
    )
    return SessionResponse(user_id=user_id, session_id=session.id)


@app.post(
    "/api/sessions/{session_id}/artifacts/{kind}",
    response_model=UploadResponse,
)
async def upload_artifact(
    session_id: str,
    kind: str,
    user_id: str = Query(...),
    file: UploadFile = File(...),
) -> UploadResponse:
    await require_session(user_id, session_id)

    content_type = (file.content_type or "").lower()
    if kind == "image":
        allowed = IMAGE_MIME_TYPES
        artifact_base = "inputs/image"
    elif kind == "video":
        allowed = VIDEO_MIME_TYPES
        artifact_base = "inputs/video"
    elif kind == "audio":
        allowed = AUDIO_MIME_TYPES
        artifact_base = "inputs/audio"
    else:
        raise HTTPException(status_code=400, detail="Artifact kind must be image, video, or audio.")

    if content_type not in allowed:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported {kind} MIME type: {content_type or 'unknown'}",
        )

    data = await file.read()
    log_event(
        logger,
        logging.INFO,
        "Artifact received",
        event_type="artifact_upload_start",
        session_id=session_id,
        status="started",
        artifact_kind=kind,
        mime_type=content_type,
        size_bytes=len(data),
    )
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds the {settings.max_upload_mb} MB prototype limit.",
        )

    extension = MIME_EXTENSION.get(content_type)
    if extension is None:
        guessed = mimetypes.guess_extension(content_type) or Path(file.filename or "").suffix
        extension = guessed or ".bin"
    artifact_key = f"{artifact_base}-{uuid.uuid4().hex[:10]}{extension}"

    artifact_service = runtime.require_artifact_service()
    version = await artifact_service.save_artifact(
        app_name=settings.app_name,
        user_id=user_id,
        session_id=session_id,
        filename=artifact_key,
        artifact=types.Part.from_bytes(data=data, mime_type=content_type),
        custom_metadata={
            "original_filename": file.filename or artifact_key,
            "kind": kind,
        },
    )
    metadata = await artifact_service.get_artifact_version(
        app_name=settings.app_name,
        user_id=user_id,
        session_id=session_id,
        filename=artifact_key,
        version=version,
    )
    if metadata is None or not metadata.canonical_uri:
        raise HTTPException(status_code=500, detail="Artifact URI could not be resolved.")

    log_event(
        logger,
        logging.INFO,
        "Artifact stored",
        event_type="artifact_upload_complete",
        session_id=session_id,
        status="success",
        artifact_kind=kind,
        mime_type=content_type,
        size_bytes=len(data),
        artifact_key=artifact_key,
        artifact_version=version,
    )
    return UploadResponse(
        artifact=ArtifactRef(
            key=artifact_key,
            version=version,
            uri=metadata.canonical_uri,
            mime_type=content_type,
        )
    )


@app.get("/api/sessions/{session_id}/artifacts/content")
async def get_artifact_content(
    session_id: str,
    user_id: str,
    key: str,
    version: int | None = None,
) -> Response:
    started = time.perf_counter()
    await require_artifact_session(user_id, session_id)
    artifact_service = runtime.require_artifact_service()
    part = await artifact_service.load_artifact(
        app_name=settings.app_name,
        user_id=user_id,
        session_id=session_id,
        filename=key,
        version=version,
    )
    if part is None:
        raise HTTPException(status_code=404, detail="Artifact not found.")
    if part.inline_data and part.inline_data.data is not None:
        payload = part.inline_data.data
        log_event(
            logger,
            logging.INFO,
            "Artifact content served",
            event_type="artifact_content_served",
            session_id=session_id,
            status="success",
            artifact_key=key,
            artifact_version=version,
            size_bytes=len(payload),
            duration_ms=round((time.perf_counter() - started) * 1000),
        )
        return Response(
            content=payload,
            media_type=part.inline_data.mime_type or "application/octet-stream",
            headers={"Cache-Control": "private, max-age=60"},
        )
    if part.text is not None:
        return Response(content=part.text, media_type="text/plain; charset=utf-8")
    raise HTTPException(status_code=500, detail="Unsupported artifact payload.")


def _content_from_chat(request: ChatRequest, session_id: str = "") -> types.Content:
    text = request.message.strip() or "Please review the attached media and continue our Iyal.ai conversation."
    if session_id:
        text += booking_context(session_id)
    if request.attachments:
        refs = [
            f"- kind={attachment.mime_type.split('/')[0]} uri={attachment.uri} mime={attachment.mime_type}"
            for attachment in request.attachments
        ]
        text += (
            "\n\nAttachment references available to tools:\n"
            + "\n".join(refs)
            + "\nUse these URIs only when a tool requires the corresponding uploaded artifact."
        )
    parts: list[types.Part] = [types.Part.from_text(text=text)]
    for attachment in request.attachments:
        parts.append(types.Part.from_uri(file_uri=attachment.uri, mime_type=attachment.mime_type))
    return types.Content(role="user", parts=parts)


@app.post("/api/sessions/{session_id}/transcribe", response_model=TranscriptionResponse)
async def transcribe_voice(
    session_id: str,
    user_id: str = Query(...),
    file: UploadFile = File(...),
) -> TranscriptionResponse:
    """Convert a short mic recording to editable text before agent submission."""
    await require_session(user_id, session_id)
    content_type = (file.content_type or "").lower().split(";", 1)[0]
    if content_type not in AUDIO_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported audio MIME type: {content_type or 'unknown'}",
        )

    data = await file.read()
    max_bytes = settings.max_transcription_mb * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Voice recording exceeds the {settings.max_transcription_mb} MB transcription limit.",
        )

    try:
        transcript = await asyncio.to_thread(transcribe_audio_bytes, data, content_type)
    except Exception as exc:
        log_event(
            logger,
            logging.ERROR,
            "Voice dictation transcription failed",
            event_type="voice_transcription_error",
            session_id=session_id,
            status="error",
            error_type=type(exc).__name__,
        )
        raise HTTPException(status_code=502, detail="Voice transcription failed. Please try again.") from exc

    log_event(
        logger,
        logging.INFO,
        "Voice dictation ready for review",
        event_type="voice_transcription_ready",
        session_id=session_id,
        status="success",
        transcript_chars=len(transcript),
    )
    return TranscriptionResponse(transcript=transcript, model=settings.gemini_transcription_model)


@app.post("/api/sessions/{session_id}/chat")
async def chat(
    session_id: str,
    http_request: Request,
    request: ChatRequest,
) -> StreamingResponse:
    await require_session(request.user_id, session_id)
    if not request.message.strip() and not request.attachments:
        raise HTTPException(status_code=400, detail="Send text or at least one attachment.")

    return StreamingResponse(
        stream_agent_run(
            user_id=request.user_id,
            session_id=session_id,
            message=_content_from_chat(request, session_id),
            heartbeat_seconds=settings.sse_heartbeat_seconds,
            is_disconnected=http_request.is_disconnected,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/sessions/{session_id}/support/slots")
async def support_slots(session_id: str, user_id: str = Query(...)) -> dict:
    await require_session(user_id, session_id)
    return {
        "status": "ready",
        "visit_types": ["video_review", "in_person"],
        "available_dates": get_available_slots(),
    }


@app.post(
    "/api/sessions/{session_id}/support/book",
    response_model=SupportBookingResponse,
)
async def support_book(
    session_id: str,
    request: SupportBookingRequest,
) -> SupportBookingResponse:
    await require_session(request.user_id, session_id)
    try:
        booking = create_booking(
            session_id=session_id,
            user_id=request.user_id,
            visit_date=request.date,
            time_slot=request.time_slot,
            visit_type=request.visit_type,
            email=request.email.strip(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    email_status = booking["email_status"]
    if email_status == "sent":
        email_phrase = "Appointment details have been sent to your email."
    elif email_status == "simulated":
        email_phrase = "Confirmation email: simulated in this demo."
    else:
        email_phrase = (
            "The visit is reserved, but the confirmation email could not be sent. "
            "Please keep the booking ID shown here."
        )

    return SupportBookingResponse(
        booking_id=booking["booking_id"],
        date=booking["date"],
        time_slot=booking["time_slot"],
        visit_type=booking["visit_type"],
        email_status=email_status,
        message=(
            f"Your product-support visit is confirmed for {booking['date']} at {booking['time_slot']}. "
            + email_phrase
        ),
    )


@app.post(
    "/api/sessions/{session_id}/outcomes",
    response_model=OutcomeFeedbackResponse,
)
async def submit_outcome(
    session_id: str,
    request: OutcomeFeedbackRequest,
    background_tasks: BackgroundTasks,
) -> OutcomeFeedbackResponse:
    session = await require_session(request.user_id, session_id)
    try:
        outcome = record_outcome(
            session_id=session_id,
            user_id=request.user_id,
            outcome=request.outcome,
            comment=request.comment,
            design_version=request.design_version,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    log_event(
        logger,
        logging.INFO,
        "Adaptation outcome captured",
        event_type="adaptation_outcome",
        session_id=session_id,
        status="success",
        outcome=outcome["outcome"],
        design_version=outcome.get("design_version"),
    )
    if settings.managed_memory_enabled:
        fact = outcome_memory_fact(outcome["outcome"], design_state=dict(session.state or {}))
        background_tasks.add_task(
            write_direct_memory,
            user_id=request.user_id,
            fact=fact,
            category="adaptation_outcome",
            session_id=session_id,
        )
        log_event(
            logger,
            logging.INFO,
            "Adaptation outcome queued for Memory Bank",
            event_type="memory_candidate_created",
            session_id=session_id,
            status="queued",
            category="adaptation_outcome",
        )
    return OutcomeFeedbackResponse(
        outcome_id=outcome["outcome_id"],
        outcome=outcome["outcome"],
        message="Thanks — this outcome will help Iyal.ai learn which adaptations work in practice.",
    )


@app.post("/api/sessions/{session_id}/analyze")
async def analyze(session_id: str, http_request: Request, request: AnalyzeRequest) -> StreamingResponse:
    """Backward-compatible endpoint for the original v0.1 form UI."""
    chat_request = ChatRequest(
        user_id=request.user_id,
        message=(
            f"Challenge: {request.challenge}\n"
            f"Desired outcome: {request.desired_outcome}\n"
            f"Preferences: {request.preferences or 'none'}\n"
            "Please analyze the attached object image and usage video."
        ),
        attachments=[request.image, request.video],
    )
    return await chat(session_id, http_request, chat_request)


@app.post("/api/sessions/{session_id}/refine")
async def refine(session_id: str, http_request: Request, request: RefineRequest) -> StreamingResponse:
    """Backward-compatible endpoint; v0.2 frontend sends refinements through /chat."""
    chat_request = ChatRequest(user_id=request.user_id, message=request.instruction)
    return await chat(session_id, http_request, chat_request)


# Keep this last: the landing site is a catch-all mount at "/".
if not mount_landing_site(app):
    app.add_api_route("/", root, methods=["GET"])
