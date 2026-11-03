import socket
import time

import pytest


class NetworkAccessBlocked(RuntimeError):
    pass


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    """Fail any test that tries to open a network connection."""

    def guard(*args, **kwargs):
        raise NetworkAccessBlocked("Network access is blocked in the test suite.")

    monkeypatch.setattr(socket.socket, "connect", guard)
    monkeypatch.setattr(socket.socket, "connect_ex", guard)
    monkeypatch.setattr(socket, "create_connection", guard)
    monkeypatch.setattr(socket, "getaddrinfo", guard)


@pytest.fixture(autouse=True)
def block_real_sleep(monkeypatch):
    """Tests must inject a fake sleep; a real 30 s retry wait would fail here instead."""

    def guard(seconds):
        raise AssertionError(f"Real sleep({seconds}) called in a test; inject a fake sleep.")

    monkeypatch.setattr(time, "sleep", guard)
