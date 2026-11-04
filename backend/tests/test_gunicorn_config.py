import importlib.util
from pathlib import Path

CONFIG = Path(__file__).resolve().parents[1] / "gunicorn.conf.py"


def load_config(monkeypatch, port=None):
    if port is None:
        monkeypatch.delenv("PORT", raising=False)
    else:
        monkeypatch.setenv("PORT", port)
    spec = importlib.util.spec_from_file_location("gunicorn_conf", CONFIG)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_worker_timeout_allows_slow_analyses_and_cold_starts(monkeypatch):
    config = load_config(monkeypatch)
    assert config.timeout >= 120
    assert config.workers == 1 and config.threads >= 2


def test_binds_to_the_platform_port(monkeypatch):
    assert load_config(monkeypatch, "10000").bind == "0.0.0.0:10000"
    assert load_config(monkeypatch).bind == "0.0.0.0:8000"


def test_access_log_leaves_out_queries_ips_and_browser_details(monkeypatch):
    log_format = load_config(monkeypatch).access_log_format
    for field in ("%(r)s", "%(q)s", "%(h)s", "%(a)s", "%(f)s", "%(u)s", "%({"):
        assert field not in log_format
    assert "%(U)s" in log_format and "%(s)s" in log_format  # path without the query, and status
