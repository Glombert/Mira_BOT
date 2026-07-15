"""Тесты rich_tg: детектор структуры и конвертация markdown → rich-блоки."""

from tools import rich_tg


def test_structure_detector():
    assert rich_tg.has_rich_structure("# Заголовок\nтекст")
    assert rich_tg.has_rich_structure("| a | b |\n|---|---|\n| 1 | 2 |")
    assert rich_tg.has_rich_structure("```py\nprint(1)\n```")
    assert rich_tg.has_rich_structure("- пункт")
    assert not rich_tg.has_rich_structure("Просто текст. Даже с | палкой внутри.")
    assert not rich_tg.has_rich_structure("")


def test_md_heading_paragraph_and_bold():
    blocks = rich_tg.md_to_rich_blocks("# Итоги\n\nВсё **хорошо**.")
    assert blocks[0] == {"type": "section_heading", "text": "Итоги", "parse_mode": "HTML"}
    assert blocks[1]["type"] == "paragraph"
    assert "<strong>хорошо</strong>" in blocks[1]["text"]


def test_md_code_fence_with_language():
    blocks = rich_tg.md_to_rich_blocks("```python\nx = 1\n```")
    assert blocks == [{"type": "preformatted", "text": "x = 1", "language": "python"}]


def test_md_lists():
    blocks = rich_tg.md_to_rich_blocks("1. один\n2. два")
    assert blocks[0]["type"] == "list"
    assert blocks[0]["is_ordered"] is True
    assert [i["text"] for i in blocks[0]["items"]] == ["один", "два"]


def test_md_table():
    blocks = rich_tg.md_to_rich_blocks("| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |")
    t = blocks[0]
    assert t["type"] == "table"
    assert t["columns"] == 2
    assert t["header_rows"] == 1
    assert [c["text"] for c in t["cells"]] == ["a", "b", "1", "2", "3", "4"]


def test_md_quote_and_divider():
    blocks = rich_tg.md_to_rich_blocks("> мысль\n\n---\n\nконец")
    assert blocks[0]["type"] == "block_quotation"
    assert blocks[0]["text"] == "мысль"
    assert blocks[1] == {"type": "divider"}
    assert blocks[2]["type"] == "paragraph"


def test_send_rich_without_token(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    assert rich_tg.send_rich(1, "# x") is False
