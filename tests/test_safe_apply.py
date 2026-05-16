"""Тесты для tools/safe_apply.py — атомарное применение и откат.

Самые важные — проверки rollback'a. Если эта логика сломается, /evolve
может оставить проект в полу-применённом состоянии. Каждый сценарий
делает фейковый проект в tmp_path и проверяет состояние ДО и ПОСЛЕ.
"""

import os
import pytest

from tools.safe_apply import safe_apply, ApplyResult


def _setup_project(root):
    """Минимальный фейковый проект."""
    (root / "tools").mkdir()
    (root / "agents").mkdir()
    (root / "tests").mkdir()
    (root / "agent.py").write_text(
        "VERSION = 1\n\ndef hello():\n    return 'old'\n",
        encoding="utf-8",
    )
    (root / "agents" / "alpha.json").write_text(
        '{"name": "alpha", "version": 1}',
        encoding="utf-8",
    )


@pytest.fixture
def project(tmp_path):
    _setup_project(tmp_path)
    return tmp_path


def _no_smoke(_root):
    return True, ""


def _failing_smoke(_root):
    return False, "fake smoke error"


# ---------------------------------------------------------------------------
# Базовые сценарии успеха
# ---------------------------------------------------------------------------

def test_modify_single_file(project):
    diff = """--- a/agent.py
+++ b/agent.py
@@ -1 +1 @@
-VERSION = 1
+VERSION = 2
"""
    result = safe_apply(diff, project_root=str(project), smoke_test_fn=_no_smoke)
    assert result.ok, result.message
    assert "VERSION = 2" in (project / "agent.py").read_text()
    assert result.touched_paths == ["agent.py"]


def test_create_new_file(project):
    diff = """--- /dev/null
+++ b/tools/new_module.py
@@ -0,0 +1,3 @@
+def greet():
+    return 'hi'
+
"""
    result = safe_apply(diff, project_root=str(project), smoke_test_fn=_no_smoke)
    assert result.ok, result.message
    new_file = project / "tools" / "new_module.py"
    assert new_file.exists()
    assert "def greet" in new_file.read_text()


def test_delete_file(project):
    diff = """--- a/agents/alpha.json
+++ /dev/null
@@ -1 +0,0 @@
-{"name": "alpha", "version": 1}
"""
    result = safe_apply(diff, project_root=str(project), smoke_test_fn=_no_smoke)
    assert result.ok
    assert not (project / "agents" / "alpha.json").exists()


def test_multi_file_modify_and_create(project):
    diff = """--- a/agent.py
+++ b/agent.py
@@ -1 +1 @@
-VERSION = 1
+VERSION = 2
--- /dev/null
+++ b/agents/artist.json
@@ -0,0 +1 @@
+{"name": "artist", "role": "specialist"}
"""
    result = safe_apply(diff, project_root=str(project), smoke_test_fn=_no_smoke)
    assert result.ok
    assert "VERSION = 2" in (project / "agent.py").read_text()
    assert (project / "agents" / "artist.json").exists()


# ---------------------------------------------------------------------------
# Откаты — главная защита
# ---------------------------------------------------------------------------

def test_rollback_on_smoke_test_failure(project):
    """Smoke-test упал — все файлы должны вернуться к исходному состоянию."""
    original_agent = (project / "agent.py").read_text()
    original_alpha = (project / "agents" / "alpha.json").read_text()

    diff = """--- a/agent.py
+++ b/agent.py
@@ -1 +1 @@
-VERSION = 1
+VERSION = 2
--- a/agents/alpha.json
+++ b/agents/alpha.json
@@ -1 +1 @@
-{"name": "alpha", "version": 1}
+{"name": "alpha", "version": 2}
"""
    result = safe_apply(diff, project_root=str(project), smoke_test_fn=_failing_smoke)
    assert not result.ok
    assert "smoke-test" in result.message

    # Содержимое — оригинальное
    assert (project / "agent.py").read_text() == original_agent
    assert (project / "agents" / "alpha.json").read_text() == original_alpha


def test_rollback_removes_created_files_on_failure(project):
    """Если создание файла прошло, но потом упало — созданный файл должен исчезнуть."""
    diff = """--- /dev/null
+++ b/tools/new_one.py
@@ -0,0 +1 @@
+x = 1
--- a/agent.py
+++ b/agent.py
@@ -1 +1 @@
-VERSION = 1
+VERSION = 2
"""
    result = safe_apply(diff, project_root=str(project), smoke_test_fn=_failing_smoke)
    assert not result.ok
    # Созданный файл должен быть удалён откатом
    assert not (project / "tools" / "new_one.py").exists()


def test_rollback_restores_deleted_file(project):
    """Удаление + потом провал → файл должен вернуться."""
    original_alpha = (project / "agents" / "alpha.json").read_text()

    diff = """--- a/agents/alpha.json
+++ /dev/null
@@ -1 +0,0 @@
-{"name": "alpha", "version": 1}
"""
    result = safe_apply(diff, project_root=str(project), smoke_test_fn=_failing_smoke)
    assert not result.ok
    assert (project / "agents" / "alpha.json").exists()
    assert (project / "agents" / "alpha.json").read_text() == original_alpha


def test_rollback_on_invalid_python_syntax(project):
    """Diff приносит синтаксическую ошибку в .py → validate_content отказ → откат."""
    original = (project / "agent.py").read_text()
    diff = """--- a/agent.py
+++ b/agent.py
@@ -3,1 +3,1 @@
-def hello():
+def hello(:
"""
    result = safe_apply(diff, project_root=str(project), smoke_test_fn=_no_smoke)
    assert not result.ok
    assert "SyntaxError" in result.message
    assert (project / "agent.py").read_text() == original


def test_rollback_on_invalid_json(project):
    """Diff приносит сломанный JSON → откат."""
    original = (project / "agents" / "alpha.json").read_text()
    diff = """--- a/agents/alpha.json
+++ b/agents/alpha.json
@@ -1 +1 @@
-{"name": "alpha", "version": 1}
+{"name": "alpha", "version
"""
    result = safe_apply(diff, project_root=str(project), smoke_test_fn=_no_smoke)
    assert not result.ok
    assert "JSON" in result.message
    assert (project / "agents" / "alpha.json").read_text() == original


# ---------------------------------------------------------------------------
# Защита whitelist
# ---------------------------------------------------------------------------

def test_rejects_diff_to_env_file(project):
    """Попытка переписать .env даже с валидным синтаксисом — отказ."""
    diff = """--- /dev/null
+++ b/.env
@@ -0,0 +1 @@
+SECRET=stolen
"""
    result = safe_apply(diff, project_root=str(project), smoke_test_fn=_no_smoke)
    assert not result.ok
    assert "Запрещённые" in result.message or "пути" in result.message
    assert not (project / ".env").exists()


def test_rejects_diff_to_memory(project):
    diff = """--- /dev/null
+++ b/memory/sessions/owner.json
@@ -0,0 +1 @@
+[]
"""
    result = safe_apply(diff, project_root=str(project), smoke_test_fn=_no_smoke)
    assert not result.ok


def test_rejects_path_traversal(project):
    diff = """--- /dev/null
+++ b/../etc/passwd
@@ -0,0 +1 @@
+root:x:0:0
"""
    result = safe_apply(diff, project_root=str(project), smoke_test_fn=_no_smoke)
    assert not result.ok


def test_rejects_random_unlisted_path(project):
    diff = """--- /dev/null
+++ b/random_file.py
@@ -0,0 +1 @@
+x = 1
"""
    result = safe_apply(diff, project_root=str(project), smoke_test_fn=_no_smoke)
    assert not result.ok


# ---------------------------------------------------------------------------
# Прочие сценарии
# ---------------------------------------------------------------------------

def test_empty_diff_rejected(project):
    result = safe_apply("", project_root=str(project))
    assert not result.ok


def test_garbage_diff_rejected(project):
    result = safe_apply("просто текст без diff", project_root=str(project))
    assert not result.ok


def test_input_diff_saved_for_debugging(project):
    """Каждое применение сохраняет копию diff'а в backup_dir/_input.diff."""
    diff = """--- a/agent.py
+++ b/agent.py
@@ -1 +1 @@
-VERSION = 1
+VERSION = 2
"""
    result = safe_apply(diff, project_root=str(project), smoke_test_fn=_no_smoke)
    assert result.ok
    diff_log = os.path.join(result.backup_dir, "_input.diff")
    assert os.path.exists(diff_log), "diff должен быть сохранён для debug"
    assert "VERSION = 2" in open(diff_log, encoding="utf-8").read()


def test_input_diff_saved_even_on_rollback(project):
    """При откате diff должен остаться — он нужен для разбора провала."""
    diff = """--- a/agent.py
+++ b/agent.py
@@ -1 +1 @@
-VERSION = 1
+VERSION =
"""  # сломанный синтаксис
    result = safe_apply(diff, project_root=str(project), smoke_test_fn=_no_smoke)
    assert not result.ok
    diff_log = os.path.join(result.backup_dir, "_input.diff")
    assert os.path.exists(diff_log)


def test_strict_diff_rejected_with_wrong_context(project):
    """Diff с устаревшим контекстом отбивается strict-проверкой."""
    diff = """--- a/agent.py
+++ b/agent.py
@@ -1 +1 @@
-NONEXISTENT_LINE
+VERSION = 2
"""
    result = safe_apply(diff, project_root=str(project), smoke_test_fn=_no_smoke)
    assert not result.ok
    # Оригинал не тронут
    assert "VERSION = 1" in (project / "agent.py").read_text()


def test_backup_dir_created(project):
    diff = """--- a/agent.py
+++ b/agent.py
@@ -1 +1 @@
-VERSION = 1
+VERSION = 2
"""
    result = safe_apply(diff, project_root=str(project), smoke_test_fn=_no_smoke)
    assert result.backup_dir is not None
    assert os.path.isdir(result.backup_dir)
    # Бэкап оригинального agent.py должен быть в backup_dir
    backup_file = os.path.join(result.backup_dir, "agent.py")
    assert os.path.exists(backup_file)
    assert "VERSION = 1" in open(backup_file, encoding="utf-8").read()


def test_smoke_test_runs_when_default(project):
    """Запуск с реальным smoke_test_fn должен попытаться сделать subprocess."""
    diff = """--- a/agent.py
+++ b/agent.py
@@ -1 +1 @@
-VERSION = 1
+VERSION = 2
"""
    # Без _no_smoke — берётся дефолтный, который попытается импортировать
    # модули из tmp_path. agent.py там — заглушка с VERSION=2, без зависимостей,
    # но `import providers` упадёт (его нет). Откат должен сработать.
    result = safe_apply(diff, project_root=str(project))
    assert not result.ok
    assert "smoke-test" in result.message
    # Откат восстановил
    assert "VERSION = 1" in (project / "agent.py").read_text()
