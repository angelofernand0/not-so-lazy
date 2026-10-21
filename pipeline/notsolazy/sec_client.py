"""The only HTTP entry point for SEC requests: identity, shared throttle and cache."""

from __future__ import annotations

import hashlib
import json
import random
import sqlite3
import time
from collections.abc import Callable
from contextlib import closing
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

import httpx

from notsolazy.config import Settings
from notsolazy.storage import BlobStore

SEC_HOSTS = frozenset({"www.sec.gov", "data.sec.gov"})


class TokenBucket:
    """Capacity-one bucket persisted in SQLite, shared by processes and clients.

    A single token prevents request bursts. Every request, including retries,
    consumes one token. All workers must use the same state_path.
    """

    def __init__(
        self,
        state_path: Path,
        rate: float = 8,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not 0 < rate <= 8:
            raise ValueError("SEC rate must be greater than zero and at most 8 requests/second.")
        self.rate, self.clock, self.sleep = rate, clock, sleep
        state_path.parent.mkdir(parents=True, exist_ok=True)
        self.path = state_path
        with closing(sqlite3.connect(self.path, timeout=30)) as db, db:
            db.execute(
                "CREATE TABLE IF NOT EXISTS bucket (id INTEGER PRIMARY KEY, tokens REAL, at REAL)"
            )
            db.execute("INSERT OR IGNORE INTO bucket VALUES (1, 1, ?)", (self.clock(),))

    def acquire(self) -> None:
        while True:
            with closing(sqlite3.connect(self.path, timeout=30, isolation_level=None)) as db:
                db.execute("BEGIN IMMEDIATE")
                row = db.execute("SELECT tokens, at FROM bucket WHERE id=1").fetchone()
                assert row is not None
                now = self.clock()
                # Backward clock jumps must delay access rather than grant extra tokens.
                at = max(now, float(row[1]))
                tokens = min(1.0, float(row[0]) + max(0, now - float(row[1])) * self.rate)
                if tokens >= 1 - 1e-9:
                    db.execute("UPDATE bucket SET tokens=0, at=? WHERE id=1", (at,))
                    db.execute("COMMIT")
                    return
                wait = (1 - tokens) / self.rate + max(0, float(row[1]) - now)
                db.execute("UPDATE bucket SET tokens=?, at=? WHERE id=1", (tokens, at))
                db.execute("COMMIT")
            self.sleep(wait)


class SecClient:
    def __init__(
        self,
        settings: Settings,
        store: BlobStore,
        *,
        transport: httpx.BaseTransport | None = None,
        limiter: TokenBucket | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.time,
        jitter: Callable[[], float] = random.random,
    ) -> None:
        identity = settings.require_sec_identity()
        self.store, self.sleep, self.clock, self.jitter = store, sleep, clock, jitter
        self.limiter = limiter or TokenBucket(
            settings.data_dir / ".sec-rate.sqlite", settings.sec_requests_per_second
        )
        self.http = httpx.Client(
            headers={"User-Agent": identity, "Accept-Encoding": "gzip, deflate"},
            timeout=30,
            follow_redirects=False,
            transport=transport,
        )

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> SecClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def get_bytes(
        self,
        url: str,
        *,
        cache_key: str | None = None,
        max_age: float | None = None,
        refresh: bool = False,
    ) -> bytes:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in SEC_HOSTS
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
        ):
            raise ValueError("SEC requests must use an approved HTTPS SEC host.")
        key = cache_key or f"http/{hashlib.sha256(url.encode()).hexdigest()}"
        metadata_key = f"http-meta/{hashlib.sha256(key.encode()).hexdigest()}.json"
        if self.store.exists(key) and not refresh:
            if max_age is None:
                return self.store.read(key)
            if self.store.exists(metadata_key):
                metadata = json.loads(self.store.read(metadata_key))
                if self.clock() - float(metadata["fetched_at"]) < max_age:
                    return self.store.read(key)
        response: httpx.Response | None = None
        for attempt in range(6):
            self.limiter.acquire()
            try:
                response = self.http.get(url)
            except httpx.TransportError:
                if attempt == 5:
                    raise
                self.sleep(2**attempt + self.jitter())
                continue
            if response.status_code != 429 and not 500 <= response.status_code < 600:
                response.raise_for_status()
                break
            if attempt == 5:
                response.raise_for_status()
            delay = 2**attempt + self.jitter()
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    delay = max(delay, float(retry_after))
                except ValueError:
                    try:
                        delay = max(
                            delay, parsedate_to_datetime(retry_after).timestamp() - self.clock()
                        )
                    except (ValueError, TypeError, OverflowError):
                        pass
            self.sleep(delay)
        assert response is not None
        payload = response.content
        self.store.write(key, payload)
        self.store.write(
            metadata_key,
            json.dumps(
                {
                    "url": url,
                    "fetched_at": self.clock(),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                    "fetched_at_iso": datetime.fromtimestamp(self.clock(), UTC).isoformat(),
                }
            ).encode(),
        )
        return payload

    def cache_metadata(self, key: str) -> dict[str, Any] | None:
        metadata_key = f"http-meta/{hashlib.sha256(key.encode()).hexdigest()}.json"
        if not self.store.exists(metadata_key):
            return None
        return cast(dict[str, Any], json.loads(self.store.read(metadata_key)))

    def get_json(self, url: str, *, refresh: bool = False) -> dict[str, Any]:
        payload = json.loads(self.get_bytes(url, max_age=86400, refresh=refresh))
        if not isinstance(payload, dict):
            raise ValueError("Expected a JSON object from SEC.")
        return cast(dict[str, Any], payload)
