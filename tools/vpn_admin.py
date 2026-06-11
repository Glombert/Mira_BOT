"""tools/vpn_admin.py — заведение VPN-пользователей через инструмент Миры.

Owner-only: оборачивает scripts/wg_add_peer.sh и reality_add_user.sh.
Скрипты делают привилегированные вещи (wg set, docker restart, правка
конфигов), поэтому доступ строго владельцу — проверяем статус в самой
функции, не полагаясь только на allowed_tools.
"""

import logging
import re
import subprocess

from tools.paths import at_root

logger = logging.getLogger("Ouroboros")

# Имя — для подписи на экране VPN. Без shell-метасимволов (argv, не shell=True,
# но валидируем для предсказуемости и понятных имён).
_NAME_RE = re.compile(r"^[\w \-().]{1,40}$", re.UNICODE)

_SCRIPTS = {
    "wireguard": "wg_add_peer.sh",
    "reality":   "reality_add_user.sh",
}

_REMOVE_SCRIPTS = {
    "wireguard": "wg_remove_peer.sh",
    "reality":   "reality_remove_user.sh",
}

# Синонимы протокола от пользователя → канон.
_PROTO_ALIASES = {
    "wireguard": "wireguard", "wg": "wireguard", "вг": "wireguard",
    "reality": "reality", "hiddify": "reality", "vless": "reality",
    "хиддифай": "reality", "реалити": "reality",
}


def _is_owner(user_id: str) -> bool:
    from tools import db
    profile = db.load_user_profile(user_id)
    return bool(profile and profile.get("status") == "owner")


def _extract_link(stdout: str) -> str:
    for line in stdout.splitlines():
        s = line.strip()
        if s.startswith(("wireguard://", "vless://")):
            return s
    return ""


def vpn_add_user(name: str, protocol: str, caller_id: str = "") -> dict:
    """Заводит VPN-пользователя и возвращает готовую ссылку для вставки.

    protocol: 'wireguard' (домашний WG) или 'reality' (Hiddify/vless).
    Только для владельца.
    """
    if not _is_owner(caller_id):
        return {"ok": False, "error": "Заводить VPN-пользователей может только владелец."}

    name = (name or "").strip()
    if not _NAME_RE.match(name):
        return {"ok": False, "error": "Имя 1–40 символов: буквы, цифры, пробел, дефис, скобки."}

    proto = _PROTO_ALIASES.get((protocol or "").strip().lower())
    if not proto:
        return {"ok": False, "error": "Укажи протокол: 'wireguard' (WG) или 'reality' (Hiddify)."}

    script = at_root("scripts", _SCRIPTS[proto])
    try:
        result = subprocess.run(
            ["bash", script, name],
            capture_output=True, text=True, timeout=90,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Скрипт VPN не уложился в 90с (sing-box рестарт завис?)."}
    except FileNotFoundError:
        return {"ok": False, "error": "bash не найден."}

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()[-300:]
        logger.warning(f"vpn_add_user {proto} '{name}' rc={result.returncode}: {err}")
        return {"ok": False, "error": f"Не удалось завести: {err or 'ошибка скрипта'}"}

    link = _extract_link(result.stdout)
    if not link:
        return {"ok": False, "error": "Пользователь заведён, но ссылку извлечь не вышло — глянь сервер."}

    logger.info(f"vpn_add_user: {proto} '{name}' заведён")
    return {
        "ok": True,
        "name": name,
        "protocol": proto,
        "link": link,
        "hint": "Скопируй ссылку и вставь её в Hiddify/v2rayNG (Reality) или WireGuard.",
    }


def vpn_remove_user(name: str, protocol: str, caller_id: str = "") -> dict:
    """Удаляет VPN-пользователя. Только для владельца.

    protocol: 'wireguard' или 'reality'. После удаления его ссылка/конфиг
    перестают подключаться.
    """
    if not _is_owner(caller_id):
        return {"ok": False, "error": "Удалять VPN-пользователей может только владелец."}

    name = (name or "").strip()
    if not _NAME_RE.match(name):
        return {"ok": False, "error": "Имя 1–40 символов: буквы, цифры, пробел, дефис, скобки."}

    proto = _PROTO_ALIASES.get((protocol or "").strip().lower())
    if not proto:
        return {"ok": False, "error": "Укажи протокол: 'wireguard' (WG) или 'reality' (Hiddify)."}

    script = at_root("scripts", _REMOVE_SCRIPTS[proto])
    try:
        result = subprocess.run(
            ["bash", script, name],
            capture_output=True, text=True, timeout=90,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Скрипт VPN не уложился в 90с."}
    except FileNotFoundError:
        return {"ok": False, "error": "bash не найден."}

    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()[-300:]
        logger.warning(f"vpn_remove_user {proto} '{name}' rc={result.returncode}: {err}")
        return {"ok": False, "error": f"Не удалось удалить: {err or 'ошибка скрипта'}"}

    logger.info(f"vpn_remove_user: {proto} '{name}' удалён")
    return {"ok": True, "name": name, "protocol": proto,
            "message": f"Пользователь «{name}» ({proto}) удалён — его ссылка больше не работает."}
