from __future__ import annotations

from pydantic import BaseModel, Field


class SessionCreateRequest(BaseModel):
    user_id: str | None = Field(default=None, min_length=1, max_length=128)


class SessionResponse(BaseModel):
    user_id: str
    session_id: str


class ArtifactRef(BaseModel):
    key: str
    version: int
    uri: str
    mime_type: str


class UploadResponse(BaseModel):
    artifact: ArtifactRef


class ChatRequest(BaseModel):
    user_id: str
    message: str = Field(default="", max_length=4000)
    attachments: list[ArtifactRef] = Field(default_factory=list, max_length=8)


class AnalyzeRequest(BaseModel):
    """Backward-compatible request used by the original form-style UI."""

    user_id: str
    challenge: str = Field(min_length=1, max_length=2000)
    desired_outcome: str = Field(min_length=1, max_length=2000)
    preferences: str = Field(default="", max_length=1000)
    image: ArtifactRef
    video: ArtifactRef


class RefineRequest(BaseModel):
    user_id: str
    instruction: str = Field(min_length=1, max_length=2000)


class SupportBookingRequest(BaseModel):
    user_id: str
    date: str
    time_slot: str
    visit_type: str
    email: str = Field(default="", max_length=320)


class SupportBookingResponse(BaseModel):
    booking_id: str
    date: str
    time_slot: str
    visit_type: str
    email_status: str
    message: str


class TranscriptionResponse(BaseModel):
    transcript: str
    model: str



class OutcomeFeedbackRequest(BaseModel):
    user_id: str
    outcome: str
    comment: str = Field(default="", max_length=1000)
    design_version: int | None = None


class OutcomeFeedbackResponse(BaseModel):
    outcome_id: str
    outcome: str
    message: str
