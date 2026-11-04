from django.test import Client


def test_health_returns_ok():
    response = Client().get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_logs_nothing_about_the_client(caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    Client(HTTP_X_FORWARDED_FOR="203.0.113.7", HTTP_CF_CONNECTING_IP="203.0.113.8").get("/api/health")
    assert "203.0.113" not in caplog.text
    assert not [record for record in caplog.records if record.name.startswith("api")]
