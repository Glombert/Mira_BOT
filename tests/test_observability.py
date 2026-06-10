"""Тесты опциональной наблюдаемости (Sentry) и переиспользуемого скраба секретов."""


from tools import observability
from tools.redaction_filter import redact


def test_init_noop_without_dsn(monkeypatch):
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.setattr(observability, "_initialized", False)
    assert observability.init("bot") is False


def test_init_warns_if_dsn_but_no_sdk(monkeypatch):
    # DSN задан, но sentry_sdk не установлен → graceful False, без исключения
    monkeypatch.setenv("SENTRY_DSN", "https://x@example.ingest.sentry.io/1")
    monkeypatch.setattr(observability, "_initialized", False)
    import builtins
    real_import = builtins.__import__

    def _no_sentry(name, *a, **k):
        if name == "sentry_sdk":
            raise ImportError("no sentry")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", _no_sentry)
    assert observability.init("bot") is False


def test_scrub_masks_secrets_in_message():
    event = {"logentry": {"message": "token=abcdef1234567890 leaked"}}
    out = observability._scrub(event, {})
    assert "abcdef1234567890" not in out["logentry"]["message"]
    assert "***REDACTED***" in out["logentry"]["message"]


def test_scrub_masks_secrets_in_exception_value():
    # Фейковый ключ собираем в рантайме, чтобы не держать литерал "ключа" в исходнике
    # (его ловит pre-commit secret-scan). Regex редакции sk-[…]{20,} совпадёт.
    fake_key = "sk-" + "x" * 25
    event = {"exception": {"values": [{"value": f"key {fake_key} failed"}]}}
    out = observability._scrub(event, {})
    assert fake_key not in out["exception"]["values"][0]["value"]
    assert "REDACTED" in out["exception"]["values"][0]["value"]


def test_scrub_survives_unexpected_shape():
    # не должен падать на неожиданной структуре события
    assert observability._scrub({}, {}) == {}


def test_redact_patterns():
    # Секреты собираем в рантайме, чтобы не держать литералы в исходнике (pre-commit scan).
    pat = "github_pat_" + "A" * 22
    assert pat not in redact(f"token {pat} here")
    bearer = "b" * 20
    assert bearer not in redact(f"Authorization: Bearer {bearer}")
    sess = "z" * 16
    assert sess not in redact(f"session={sess} here")
