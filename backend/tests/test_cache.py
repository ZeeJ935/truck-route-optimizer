import pytest

from core.cache import TTLCache


class Clock:
    def __init__(self):
        self.now = 1_000.0

    def __call__(self):
        return self.now


def test_entries_expire_after_ttl():
    clock = Clock()
    cache = TTLCache(ttl_seconds=10, clock=clock)
    cache.set("k", "v")
    clock.now += 9.9
    assert cache.get("k") == "v"
    clock.now += 0.1
    assert cache.get("k") is None
    assert len(cache) == 0


def test_least_recently_used_entry_is_evicted_when_full():
    cache = TTLCache(ttl_seconds=10, max_entries=2, clock=Clock())
    cache.set("a", 1)
    cache.set("b", 2)
    assert cache.get("a") == 1  # "a" is now most recently used
    cache.set("c", 3)
    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3


def test_default_is_returned_for_missing_keys():
    assert TTLCache(ttl_seconds=1).get("missing", "fallback") == "fallback"


@pytest.mark.parametrize(("ttl", "size"), [(0, 1), (1, 0), (-1, 5)])
def test_invalid_configuration_rejected(ttl, size):
    with pytest.raises(ValueError):
        TTLCache(ttl_seconds=ttl, max_entries=size)
