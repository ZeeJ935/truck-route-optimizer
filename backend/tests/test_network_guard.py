import socket
import urllib.request

import pytest

from tests.conftest import NetworkAccessBlocked


def test_network_is_blocked_during_tests():
    with pytest.raises(NetworkAccessBlocked):
        socket.create_connection(("127.0.0.1", 80), timeout=1)
    with pytest.raises(NetworkAccessBlocked):
        urllib.request.urlopen("https://api.open-meteo.com/v1/forecast", timeout=1)
