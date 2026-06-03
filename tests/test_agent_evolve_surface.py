"""Guard: поверхность evolve/CLI в agent.py после чистки мёртвого кода.

Phase A — удалён старый single-file evolve-путь (не вызывался).
Phase B — удалён CLI (`python agent.py` __main__ + MODELS_CONFIG/setup_client/
print_menu/print_help + интерактивный evolve() + _evolve_show_diff). Прод
(telegram/web) идёт через _run_evolve_preview + safe_apply, ничего из этого
не используя. Тест держит границу: мёртвое/CLI не вернулось, живое не пропало.
"""

import os

os.environ.setdefault("MIRA_ALLOW_UNSANDBOXED", "1")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "t")

import agent


def test_dead_and_cli_removed():
    for name in (
        # Phase A — legacy single-file evolve
        "_apply_unified_diff",
        "_legacy_evolve_build_prompt",
        "_evolve_request_diff",
        "_evolve_check_principles",
        "_evolve_apply_and_validate",
        # Phase B — CLI
        "evolve",
        "_evolve_show_diff",
        "setup_client",
        "print_menu",
        "print_help",
        "MODELS_CONFIG",
        "alpha",
    ):
        assert not hasattr(agent, name), f"{name} — удалённый мёртвый/CLI-код, не должен возвращаться"


def test_live_evolve_path_intact():
    # Эти функции использует живой telegram-/evolve (_run_evolve_preview) + сам модуль.
    for name in (
        "_evolve_build_messages",
        "_unescape_diff",
        "_evolve_extract_diff",
        "_evolve_make_readonly_agent",
        "reflect",
        "smoke_test",
        "Agent",
        "Profile",
    ):
        assert hasattr(agent, name), f"{name} — живой символ, пропал"
