from pathlib import Path

import httpx
import pytest

from notsolazy.config import Settings
from notsolazy.sec_client import SecClient, TokenBucket
from notsolazy.storage import LocalBlobStore


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.delays: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, duration: float) -> None:
        assert duration >= 0
        self.delays.append(duration)
        self.now += duration


def client_for(tmp_path: Path, handler: object, clock: Clock) -> SecClient:
    return SecClient(
        Settings(
            _env_file=None, sec_user_agent="NotSoLazy/0.1 test@example.org", data_dir=tmp_path
        ),
        LocalBlobStore(tmp_path),
        transport=httpx.MockTransport(handler),
        limiter=TokenBucket(tmp_path / "limiter.sqlite", clock=clock.time, sleep=clock.sleep),
        clock=clock.time,
        sleep=clock.sleep,
        jitter=lambda: 0,
    )


def test_identity_required_before_request_or_storage(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="SEC_USER_AGENT"):
        SecClient(
            Settings(_env_file=None, sec_user_agent="", data_dir=tmp_path), LocalBlobStore(tmp_path)
        )
    assert not list(tmp_path.iterdir())


def test_global_bucket_shared_across_instances(tmp_path: Path) -> None:
    clock = Clock()
    first = TokenBucket(tmp_path / "shared.sqlite", clock=clock.time, sleep=clock.sleep)
    second = TokenBucket(tmp_path / "shared.sqlite", clock=clock.time, sleep=clock.sleep)
    observed = []
    for bucket in [first, second, first, second, second]:
        bucket.acquire()
        observed.append(clock.now)
    assert observed == [1000, 1000.125, 1000.25, 1000.375, 1000.5]


def test_bucket_rejects_unsafe_rate(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        TokenBucket(tmp_path / "bad.sqlite", rate=10)


def test_identity_cache_and_json_freshness(tmp_path: Path) -> None:
    clock = Clock()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["User-Agent"] == "NotSoLazy/0.1 test@example.org"
        return httpx.Response(200, json={"request": len(requests)})

    with client_for(tmp_path, handler, clock) as client:
        assert client.get_json("https://data.sec.gov/submissions/CIK0000320193.json") == {
            "request": 1
        }
        assert client.get_json("https://data.sec.gov/submissions/CIK0000320193.json") == {
            "request": 1
        }
        clock.now += 86401
        assert client.get_json("https://data.sec.gov/submissions/CIK0000320193.json") == {
            "request": 2
        }
        assert client.get_json(
            "https://data.sec.gov/submissions/CIK0000320193.json", refresh=True
        ) == {"request": 3}
    assert len(requests) == 3


def test_retry_policy_honors_retry_after_and_never_caches_errors(tmp_path: Path) -> None:
    clock = Clock()
    statuses = [429, 503, 200]

    def handler(request: httpx.Request) -> httpx.Response:
        status = statuses.pop(0)
        return httpx.Response(
            status, content=b"ok", headers={"Retry-After": "3"} if status == 429 else {}
        )

    with client_for(tmp_path, handler, clock) as client:
        assert client.get_bytes("https://www.sec.gov/files/test", cache_key="raw/test") == b"ok"
    assert clock.delays == [3, 2]


def test_retry_exhaustion_is_five_retries_and_does_not_cache(tmp_path: Path) -> None:
    clock = Clock()
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(503)

    with client_for(tmp_path, handler, clock) as client:
        with pytest.raises(httpx.HTTPStatusError):
            client.get_bytes("https://www.sec.gov/files/test", cache_key="raw/bad")
        assert not client.store.exists("raw/bad")
    assert len(requests) == 6
    assert clock.delays == [1, 2, 4, 8, 16]


def test_forbidden_host_and_redirect_are_not_followed(tmp_path: Path) -> None:
    clock = Clock()
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://example.com"})

    with client_for(tmp_path, handler, clock) as client:
        for url in [
            "http://www.sec.gov/files/x",
            "https://sec.gov.evil.test/x",
            "https://user@www.sec.gov/x",
        ]:
            with pytest.raises(ValueError):
                client.get_bytes(url)
        with pytest.raises(httpx.HTTPStatusError):
            client.get_bytes("https://www.sec.gov/files/x")
    assert len(requests) == 1


def test_transport_errors_are_retried(tmp_path: Path) -> None:
    clock = Clock()
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            raise httpx.ReadTimeout("simulated", request=request)
        return httpx.Response(200, content=b"ok")

    with client_for(tmp_path, handler, clock) as client:
        assert client.get_bytes("https://www.sec.gov/files/x") == b"ok"
    assert clock.delays == [1]


def test_shared_bucket_serializes_concurrent_callers(tmp_path: Path) -> None:
    import time
    from concurrent.futures import ThreadPoolExecutor

    first = TokenBucket(tmp_path / "shared.sqlite")
    second = TokenBucket(tmp_path / "shared.sqlite")
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda bucket: bucket.acquire(), [first, second, first, second]))
    assert time.monotonic() - start >= 0.36


def test_permanent_http_errors_are_not_retried(tmp_path: Path) -> None:
    clock = Clock()
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(404)

    with client_for(tmp_path, handler, clock) as client:
        with pytest.raises(httpx.HTTPStatusError):
            client.get_bytes("https://www.sec.gov/files/missing")
    assert len(requests) == 1
    assert not clock.delays
