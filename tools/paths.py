"""tools/paths.py — единый якорь файловых путей проекта.

Все константы путей привязываются к корню репозитория, а не к cwd:
запуск процесса из другого каталога раньше молча создавал параллельные
memory/ и logs/ (см. clients/memory/mira.db — реальный случай).
"""

import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def at_root(*parts: str) -> str:
    """Абсолютный путь от корня проекта."""
    return os.path.join(PROJECT_ROOT, *parts)
