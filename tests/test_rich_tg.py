"""Тесты rich_tg: детектор структуры и отправка markdown как rich-сообщения."""

import json

from tools import rich_tg


def test_structure_detector():
    assert rich_tg.has_rich_structure("# Заголовок\nтекст")
    assert rich_tg.has_rich_structure("| a | b |\n|---|---|\n| 1 | 2 |")
    assert rich_tg.has_rich_structure("```py\nprint(1)\n```")
    assert rich_tg.has_rich_structure("- пункт")
    assert not rich_tg.has_rich_structure("Просто текст. Даже с | палкой внутри.")
    assert not rich_tg.has_rich_structure("")


def test_send_rich_without_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert rich_tg.send_rich(1, "# x") is False


def test_send_rich_empty_text(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    assert rich_tg.send_rich(1, "") is False
    assert rich_tg.send_rich(1, "   ") is False


def test_send_rich_over_limit(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    assert rich_tg.send_rich(1, "# x\n" + "а" * 40000) is False


def test_send_rich_payload_is_markdown(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    captured = {}

    class _Resp:
        def read(self):
            return b'{"ok": true}'
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    def _fake_urlopen(req, timeout=0):
        captured["url"] = req.full_url
        captured["payload"] = json.loads(req.data.decode())
        return _Resp()

    monkeypatch.setattr(rich_tg.urllib.request, "urlopen", _fake_urlopen)
    md = "# Итоги\n\n| a | b |\n|---|---|\n| 1 | 2 |"
    assert rich_tg.send_rich(42, md) is True
    assert captured["url"].endswith("/sendRichMessage")
    assert captured["payload"] == {"chat_id": 42, "rich_message": {"markdown": md}}


def test_send_rich_api_error_falls_back(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    import io
    import urllib.error

    def _fake_urlopen(req, timeout=0):
        raise urllib.error.HTTPError(
            req.full_url, 400, "Bad Request", {},
            io.BytesIO(b'{"ok":false,"description":"parse error"}'),
        )

    monkeypatch.setattr(rich_tg.urllib.request, "urlopen", _fake_urlopen)
    assert rich_tg.send_rich(1, "# x") is False
