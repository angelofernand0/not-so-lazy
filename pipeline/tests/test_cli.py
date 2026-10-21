import json
import sys

import pytest

from notsolazy.cli import main
from notsolazy.models import make_engine


def test_doctor_is_offline_and_redacts_credentials(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://reader:secret@localhost/nsl")
    monkeypatch.setattr(sys, "argv", ["nsl", "doctor"])
    main()
    output = capsys.readouterr().out
    assert "secret" not in output
    assert json.loads(output)["database_backend"] == "postgresql"


def test_sqlite_interface() -> None:
    engine = make_engine("sqlite:///:memory:")
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
    engine.dispose()


def test_require_sec_refuses_missing_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEC_USER_AGENT", "")
    monkeypatch.setattr(sys, "argv", ["nsl", "doctor", "--require-sec"])
    with pytest.raises(SystemExit) as error:
        main()
    assert error.value.code == 2


def test_migrations_upgrade_downgrade_and_match_models(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pathlib import Path

    from alembic import command
    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from sqlalchemy import inspect

    from notsolazy.models import Base

    url = f"sqlite:///{tmp_path / 'schema.db'}"
    monkeypatch.setenv("DATABASE_URL", url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    monkeypatch.setattr(sys, "argv", ["nsl", "init-db"])
    main()
    main()
    engine = make_engine(url)
    with engine.connect() as connection:
        assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    command.downgrade(config, "base")
    assert "filings" not in inspect(engine).get_table_names()
    command.upgrade(config, "head")
    assert "filings" in inspect(engine).get_table_names()
    engine.dispose()


def test_cli_discover_fetch_aliases_since_and_cached_rerun(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import httpx

    import notsolazy.cli as cli
    from notsolazy.sec_client import SecClient
    from notsolazy.universe import Constituent

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'cli.db'}")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "blobs"))
    monkeypatch.setenv("SEC_USER_AGENT", "NotSoLazy/0.1 test@example.org")
    monkeypatch.setattr(
        cli,
        "load_snapshot",
        lambda: [
            Constituent("GOOG", "Alphabet", "Communication Services", 1652044),
            Constituent("GOOGL", "Alphabet", "Communication Services", 1652044),
        ],
    )
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if "submissions" not in request.url.path:
            return httpx.Response(200, content=b"<html>source</html>")
        return httpx.Response(
            200,
            json={
                "fiscalYearEnd": "1231",
                "filings": {
                    "recent": {
                        "accessionNumber": ["0001652044-26-000001", "0001652044-25-000001"],
                        "reportDate": ["2025-12-31", "2024-12-31"],
                        "filingDate": ["2026-02-01", "2025-02-01"],
                        "form": ["10-K", "10-K"],
                        "primaryDocument": ["report.htm", "report.htm"],
                    },
                    "files": [],
                },
            },
        )

    monkeypatch.setattr(
        cli,
        "SecClient",
        lambda settings, store: SecClient(settings, store, transport=httpx.MockTransport(handler)),
    )
    monkeypatch.setattr(sys, "argv", ["nsl", "init-db"])
    main()
    capsys.readouterr()
    monkeypatch.setattr(sys, "argv", ["nsl", "discover", "--ticker", "GOOGL"])
    main()
    assert json.loads(capsys.readouterr().out)["cik"] == 1652044
    monkeypatch.setattr(sys, "argv", ["nsl", "fetch", "--ticker", "GOOG", "--since", "2026-03-01"])
    main()
    assert capsys.readouterr().out == ""
    assert len(requests) == 1
    monkeypatch.setattr(sys, "argv", ["nsl", "fetch", "--ticker", "GOOGL"])
    main()
    result = json.loads(capsys.readouterr().out)
    assert result["current"]["sha256"]
    assert len(requests) == 3
    main()
    assert len(requests) == 3


def test_cli_handles_company_before_its_first_annual_report(
    tmp_path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import httpx

    import notsolazy.cli as cli
    from notsolazy.sec_client import SecClient
    from notsolazy.universe import Constituent

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'new.db'}")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "blobs"))
    monkeypatch.setenv("SEC_USER_AGENT", "NotSoLazy/0.1 test@example.org")
    monkeypatch.setattr(cli, "load_snapshot", lambda: [Constituent("NEW", "New", "Test", 1)])
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "filings": {
                    "recent": {
                        "accessionNumber": [],
                        "reportDate": [],
                        "filingDate": [],
                        "form": [],
                        "primaryDocument": [],
                    },
                    "files": [],
                }
            },
        )
    )
    monkeypatch.setattr(
        cli, "SecClient", lambda settings, store: SecClient(settings, store, transport=transport)
    )
    monkeypatch.setattr(sys, "argv", ["nsl", "init-db"])
    main()
    capsys.readouterr()
    monkeypatch.setattr(sys, "argv", ["nsl", "discover", "--ticker", "NEW"])
    main()
    assert json.loads(capsys.readouterr().out)["status"] == "no_annual_filing"
    monkeypatch.setattr(sys, "argv", ["nsl", "fetch"])
    main()
    assert json.loads(capsys.readouterr().out)["status"] == "no_discovered_pair"
