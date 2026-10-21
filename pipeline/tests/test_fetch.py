from datetime import date
from pathlib import Path

import httpx

from notsolazy.config import Settings
from notsolazy.fetch import fetch_filing
from notsolazy.models import Filing
from notsolazy.sec_client import SecClient
from notsolazy.storage import LocalBlobStore


def test_fetch_uses_immutable_raw_cache_and_records_provenance(tmp_path: Path) -> None:
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=b"<html>Source</html>")

    settings = Settings(
        _env_file=None, sec_user_agent="NotSoLazy/0.1 test@example.org", data_dir=tmp_path
    )
    filing = Filing(
        accession="0000320193-25-000079",
        cik=320193,
        form="10-K",
        filed_at=date(2025, 10, 31),
        primary_doc_url="https://www.sec.gov/Archives/edgar/data/320193/filing.htm",
        status="discovered",
    )
    with SecClient(
        settings, LocalBlobStore(tmp_path), transport=httpx.MockTransport(handler)
    ) as client:
        first = fetch_filing(filing, client)
        fetched_at = filing.fetched_at
        assert fetch_filing(filing, client) == first
    assert len(requests) == 1
    assert filing.raw_blob_key == "raw/320193/0000320193-25-000079.html"
    assert filing.sha256 and len(filing.sha256) == 64
    assert filing.fetched_at == fetched_at
    assert filing.size_bytes == len(first)
    assert filing.status == "fetched"
