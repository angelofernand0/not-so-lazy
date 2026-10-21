"""Fetch primary HTML exactly once and persist its provenance."""

import hashlib
from datetime import UTC, datetime

from notsolazy.models import Filing
from notsolazy.sec_client import SecClient

FETCH_VERSION = "fetch-v1"


def fetch_filing(filing: Filing, client: SecClient) -> bytes:
    if not filing.primary_doc_url:
        raise ValueError(f"Filing {filing.accession} has no primary document.")
    key = f"raw/{filing.cik}/{filing.accession}.html"
    cached = client.store.exists(key)
    payload = client.get_bytes(filing.primary_doc_url, cache_key=key)
    filing.raw_blob_key = key
    filing.sha256 = hashlib.sha256(payload).hexdigest()
    filing.size_bytes = len(payload)
    if not cached or filing.fetched_at is None:
        metadata = client.cache_metadata(key)
        filing.fetched_at = (
            datetime.fromtimestamp(float(metadata["fetched_at"]), UTC)
            if metadata
            else datetime.now(UTC)
        )
    filing.fetch_version = FETCH_VERSION
    if filing.form != "10-K/A":
        filing.status = "fetched"
    return payload
