"""Every pipeline test is offline, including future tests."""

import socket

import pytest


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        pytest.fail("Network access is forbidden in tests; use httpx.MockTransport.", pytrace=False)

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
