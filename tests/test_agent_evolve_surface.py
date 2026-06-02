"""Guard: поверхность evolve в agent.py после чистки мёртвого legacy-кода.

Удалённые функции — старый single-file evolve-путь, не вызывался ни из
telegram-/evolve, ни из CLI evolve() (оба идут через safe_apply/diff_tools).
Тест держит границу: мёртвое не вернулось, живое не пропало.
"""

import os

os.environ.setdefault("MIRA_ALLOW_UNSANDBOXED", "1")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "t")

import agent


def test_dead_legacy_evolve_removed():
    for name in (
        "_apply_unified_diff",
        "_legacy_evolve_build_prompt",
        "_evolve_request_diff",
        "_evolve_check_principles",
        "_evolve_apply_and_validate",
    ):
        assert not hasattr(agent, name), f"{name} — мёртвый legacy-код, не должен возвращаться"


def test_live_evolve_path_intact():
    for name in (
        "_evolve_build_messages",
        "_unescape_diff",
        "_evolve_extract_diff",
        "_evolve_make_readonly_agent",
        "_evolve_show_diff",
        "evolve",
        "smoke_test",
    ):
        assert hasattr(agent, name), f"{name} — живая функция evolve-пути, пропала"
