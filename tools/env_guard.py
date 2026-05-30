"""tools/env_guard.py — проверка прав доступа к .env при старте.

Секреты (.env) должны быть читаемы только владельцем (chmod 600). Если файл
доступен группе или others — логируем предупреждение. Не падаем: на проде
файл уже мог существовать с правильными правами, а ломать старт из-за прав —
хуже, чем предупредить.

Вызывается из telegram_bot.py и web/app.py сразу после load_dotenv().
"""

import os
import stat
import logging

logger = logging.getLogger("Ouroboros")

_GROUP_OTHER_BITS = (
    stat.S_IRGRP | stat.S_IWGRP | stat.S_IXGRP
    | stat.S_IROTH | stat.S_IWOTH | stat.S_IXOTH
)


def check_env_permissions(paths: tuple[str, ...] = (".env", "../.env")) -> None:
    """Предупреждает, если .env доступен кому-то кроме владельца."""
    for name in paths:
        path = os.path.abspath(name)
        if not os.path.exists(path):
            continue
        mode = os.stat(path).st_mode
        if mode & _GROUP_OTHER_BITS:
            logger.warning(
                f"БЕЗОПАСНОСТЬ: {path} доступен другим пользователям "
                f"(права: {oct(mode & 0o777)}). Исправь: chmod 600 {path}"
            )
