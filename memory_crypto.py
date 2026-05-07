"""
memory_crypto.py — прозрачное шифрование файлов памяти.

Если MEMORY_ENCRYPTION_KEY задан в .env — все профили и сессии
шифруются симметричным Fernet-шифрованием при сохранении и
расшифровываются при чтении.

Если ключ не задан — работает как раньше, в открытом JSON.
Это позволяет включить шифрование в любой момент без миграции:
существующие файлы будут прочитаны как JSON и перезаписаны
зашифрованными при следующем сохранении.

Генерация ключа (один раз):
    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Результат добавить в .env: MEMORY_ENCRYPTION_KEY=...
"""

import os
import json
import logging

logger = logging.getLogger("Ouroborus")

_fernet = None


def init(key: str | None = None) -> None:
    """Инициализирует шифрование. Вызывается при старте после load_dotenv()."""
    global _fernet
    key = key or os.getenv("MEMORY_ENCRYPTION_KEY", "")
    if not key:
        return
    try:
        from cryptography.fernet import Fernet
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
        logger.info("memory_crypto: шифрование памяти включено")
    except ImportError:
        logger.warning(
            "memory_crypto: пакет 'cryptography' не установлен. "
            "Запусти: pip install cryptography"
        )
    except Exception as e:
        logger.warning(f"memory_crypto: не удалось инициализировать шифрование: {e}")


def is_enabled() -> bool:
    return _fernet is not None


def load_json(path: str) -> dict | list | None:
    """
    Читает JSON-файл с прозрачным расшифрованием.
    Если файл не существует — возвращает None.
    Если шифрование включено, но файл в старом формате (JSON) — читает как есть.
    """
    if not os.path.exists(path):
        return None
    try:
        with open(path, "rb") as f:
            raw = f.read()
        if not raw:
            return None

        if _fernet:
            # Fernet-токен начинается с 'gAAAA' (base64), JSON — с '{' или '['
            if raw[0:1] not in (b"{", b"["):
                decrypted = _fernet.decrypt(raw)
                return json.loads(decrypted.decode("utf-8"))

        return json.loads(raw.decode("utf-8"))

    except Exception as e:
        logger.error(f"memory_crypto.load_json({path}): {e}")
        return None


def save_json(path: str, data: dict | list) -> None:
    """
    Записывает данные в JSON-файл с прозрачным шифрованием.
    Создаёт промежуточные директории автоматически.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    try:
        raw = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        if _fernet:
            raw = _fernet.encrypt(raw)
            with open(path, "wb") as f:
                f.write(raw)
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(raw.decode("utf-8"))
    except Exception as e:
        logger.error(f"memory_crypto.save_json({path}): {e}")
        raise
