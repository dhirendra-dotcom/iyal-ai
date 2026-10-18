from __future__ import annotations

import asyncio

from app import streaming


def test_sse_heartbeat_is_comment_frame():
    heartbeat = streaming.sse_heartbeat()
    assert heartbeat == ": heartbeat\n\n"
    assert "event:" not in heartbeat
    assert "data:" not in heartbeat


def test_stream_emits_connected_and_heartbeat_while_runner_is_silent(monkeypatch):
    class FakeRunner:
        async def run_async(self, **kwargs):
            await asyncio.sleep(0.12)
            if False:
                yield None

    monkeypatch.setattr(streaming.runtime, "require_runner", lambda: FakeRunner())

    async def collect() -> list[str]:
        chunks: list[str] = []
        async for chunk in streaming.stream_agent_run(
            user_id="usr_test",
            session_id="ses_test",
            message=object(),
            heartbeat_seconds=0.05,
        ):
            chunks.append(chunk)
        return chunks

    chunks = asyncio.run(collect())
    assert chunks[0].startswith("event: connected")
    assert any(chunk == ": heartbeat\n\n" for chunk in chunks)
    assert chunks[-1].startswith("event: run_complete")
