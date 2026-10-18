from __future__ import annotations

from dataclasses import dataclass

from google.adk.apps.app import App
from google.adk.artifacts import GcsArtifactService
from google.adk.memory import VertexAiMemoryBankService
from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService, InMemorySessionService, VertexAiSessionService

from app.agent import root_agent
from app.config import settings


@dataclass
class RuntimeServices:
    artifact_service: GcsArtifactService | None = None
    session_service: object | None = None
    memory_service: object | None = None
    runner: Runner | None = None
    database_session_service: DatabaseSessionService | None = None

    async def start(self) -> None:
        self.artifact_service = GcsArtifactService(bucket_name=settings.gcs_bucket)

        if settings.managed_sessions_enabled:
            self.session_service = VertexAiSessionService(
                project=settings.google_cloud_project,
                location=settings.context_service_location,
                agent_engine_id=settings.vertex_session_runtime_id.strip(),
            )
        else:
            db_url = (settings.session_db_url or "").strip()
            if db_url:
                database_service = DatabaseSessionService(db_url)
                await database_service.prepare_tables()
                self.session_service = database_service
                self.database_session_service = database_service
            else:
                self.session_service = InMemorySessionService()

        if settings.managed_memory_enabled:
            self.memory_service = VertexAiMemoryBankService(
                project=settings.google_cloud_project,
                location=settings.context_service_location,
                # ADK currently names this parameter agent_engine_id even when
                # it contains a standalone Memory Bank resource ID.
                agent_engine_id=settings.vertex_memory_bank_id.strip(),
            )

        app = App(name=settings.app_name, root_agent=root_agent)
        runner_kwargs = {
            "app": app,
            "session_service": self.session_service,
            "artifact_service": self.artifact_service,
        }
        if self.memory_service is not None:
            runner_kwargs["memory_service"] = self.memory_service
        self.runner = Runner(**runner_kwargs)

    async def stop(self) -> None:
        if self.database_session_service is not None:
            await self.database_session_service.close()

    def require_runner(self) -> Runner:
        if self.runner is None:
            raise RuntimeError("Runtime services are not initialized.")
        return self.runner

    def require_session_service(self):
        if self.session_service is None:
            raise RuntimeError("Session service is not initialized.")
        return self.session_service

    def require_memory_service(self):
        if self.memory_service is None:
            raise RuntimeError("Memory Bank is not enabled.")
        return self.memory_service

    def require_artifact_service(self) -> GcsArtifactService:
        if self.artifact_service is None:
            raise RuntimeError("Artifact service is not initialized.")
        return self.artifact_service


runtime = RuntimeServices()
