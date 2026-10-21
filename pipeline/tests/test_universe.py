from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from notsolazy.models import Base, Company, CompanyAlias, make_engine
from notsolazy.universe import (
    Constituent,
    crosscheck,
    parse_constituents,
    refresh_snapshot,
    sync_companies,
)


def test_parse_wikipedia_and_normalize_share_class_for_crosscheck() -> None:
    payload = (
        b'<table id="constituents"><tr><th>Header</th></tr><tr><td>BRK.B</td>'
        b"<td>Berkshire</td><td>Financials</td><td>Industry</td><td>HQ</td>"
        b"<td>date</td><td>1067983</td></tr></table>"
    )
    rows = parse_constituents(payload)
    assert rows == [Constituent("BRK.B", "Berkshire", "Financials", 1067983)]
    assert not crosscheck(rows, {"0": {"ticker": "BRK-B", "cik_str": 1067983}})
    assert "SEC CIK 123" in crosscheck(rows, {"0": {"ticker": "BRK-B", "cik_str": 123}})[0]


def test_dual_class_shares_keep_one_company_and_both_aliases() -> None:
    engine = make_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        rows = [
            Constituent("GOOG", "Alphabet", "Communication Services", 1652044),
            Constituent("GOOGL", "Alphabet", "Communication Services", 1652044),
        ]
        sync_companies(session, rows)
        sync_companies(session, rows)
        assert session.scalar(select(func.count()).select_from(Company)) == 1
        assert session.scalar(select(func.count()).select_from(CompanyAlias)) == 2
        sync_companies(session, [])
        assert session.scalar(select(Company.in_sp500)) is False
    engine.dispose()


def test_refresh_mismatch_does_not_overwrite_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import Mock

    rows = "".join(
        f"<tr><td>T{i}</td><td>Test {i}</td><td>Sector</td>"
        f"<td>x</td><td>x</td><td>x</td><td>{i + 1}</td></tr>"
        for i in range(500)
    )
    payload = f'<table id="constituents"><tr><th>Heading</th></tr>{rows}</table>'.encode()
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *args, **kwargs: httpx.Response(
            200, content=payload, request=httpx.Request("GET", "https://en.wikipedia.org")
        ),
    )
    client = Mock()
    client.get_json.return_value = {
        str(i): {"ticker": f"T{i}", "cik_str": i + 2} for i in range(500)
    }
    target = tmp_path / "sp500.csv"
    target.write_text("existing snapshot")
    with pytest.raises(ValueError, match="CIK cross-check failed"):
        refresh_snapshot(client, target)
    assert target.read_text() == "existing snapshot"


def test_committed_snapshot_counts_and_checksum() -> None:
    import hashlib
    import json

    from notsolazy.universe import SNAPSHOT, load_snapshot

    metadata = json.loads(SNAPSHOT.with_suffix(".meta.json").read_text())
    rows = load_snapshot()
    assert len(rows) == metadata["security_count"]
    assert len({row.cik for row in rows}) == metadata["issuer_count"]
    assert hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest() == metadata["sha256"]
