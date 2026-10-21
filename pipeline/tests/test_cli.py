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
