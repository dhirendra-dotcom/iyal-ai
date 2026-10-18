import asyncio

from app.resilient_model import ResilientGemini, retry_before_first_chunk


def _collect(agen):
    async def run():
        return [item async for item in agen]
    return asyncio.run(run())


def _stream(items, first_delay=0.0, between=0.0):
    async def gen():
        await asyncio.sleep(first_delay)
        for i, item in enumerate(items):
            if i:
                await asyncio.sleep(between)
            yield item
    return gen()


def test_stalled_first_attempt_is_retried_and_last_attempt_has_no_limit():
    starts = []

    def start():
        starts.append(1)
        # First attempt stalls; the second is slower than the limit but must still complete.
        return _stream(["a", "b"], first_delay=1.0 if len(starts) == 1 else 0.15)

    out = _collect(retry_before_first_chunk(start, first_chunk_timeout_seconds=0.1, max_attempts=2))
    assert out == ["a", "b"]
    assert len(starts) == 2


def test_output_already_streaming_is_never_interrupted():
    starts = []

    def start():
        starts.append(1)
        return _stream(["a", "b", "c"], first_delay=0.0, between=0.2)

    out = _collect(retry_before_first_chunk(start, first_chunk_timeout_seconds=0.05, max_attempts=2))
    assert out == ["a", "b", "c"]
    assert len(starts) == 1


def test_disabled_timeout_and_single_attempt_behave_like_plain_stream():
    for timeout, attempts in ((0, 2), (0.05, 1)):
        starts = []

        def start():
            starts.append(1)
            return _stream(["x"], first_delay=0.1)

        assert _collect(retry_before_first_chunk(start, first_chunk_timeout_seconds=timeout,
                                                 max_attempts=attempts)) == ["x"]
        assert len(starts) == 1


def test_empty_stream_returns_nothing():
    assert _collect(retry_before_first_chunk(lambda: _stream([]), first_chunk_timeout_seconds=1,
                                             max_attempts=2)) == []


def test_root_agent_uses_resilient_model():
    from app.agent import root_agent

    assert isinstance(root_agent.model, ResilientGemini)
