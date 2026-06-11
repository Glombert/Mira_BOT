"""tools/vpn_tools.py — мониторинг WireGuard и РУ-моста.

Источник учёта — `wg show <iface> dump`: на каждого пира кумулятивные
rx/tx байты и unix-время последнего хендшейка. Сэмплер пишет срез раз в
5 минут; «кто сколько сидит» = сэмплы со свежим хендшейком × 5 минут.

Мост (РУ-релей) проверяется TCP-коннектом: ICMP с VPS часто закрыт,
а ssh-порт моста отвечает всегда. Латентность TCP-handshake ≈ RTT.

Имена пиров: memory/vpn_peers.json {pubkey: "подпись"} — заполняется
скриптом scripts/wg_add_peer.sh или руками. Неизвестный пир показывается
обрезанным ключом.
"""

import json
import logging
import os
import socket
import subprocess
import time

from tools.paths import at_root

logger = logging.getLogger("Ouroboros")

WG_IFACE = os.getenv("MIRA_VPN_IFACE", "wg0")
BRIDGE_ADDR = os.getenv("MIRA_VPN_BRIDGE", "5.42.98.236:22")
PEER_NAMES_PATH = at_root("memory", "vpn_peers.json")

# Хендшейк WG обновляется каждые ~2 мин при живом трафике; 3 мин = онлайн.
ONLINE_THRESHOLD_SEC = 180


def peer_names() -> dict[str, str]:
    if not os.path.exists(PEER_NAMES_PATH):
        return {}
    try:
        with open(PEER_NAMES_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"vpn_peers.json повреждён: {e}")
        return {}


def peer_label(pubkey: str) -> str:
    return peer_names().get(pubkey) or f"{pubkey[:8]}…"


def wg_dump() -> list[dict]:
    """Пиры wg-интерфейса: pubkey, возраст хендшейка, кумулятивные байты."""
    try:
        out = subprocess.run(
            ["wg", "show", WG_IFACE, "dump"],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        logger.warning(f"vpn: wg dump недоступен: {e}")
        return []
    if out.returncode != 0:
        logger.warning(f"vpn: wg dump rc={out.returncode}: {out.stderr.strip()[:120]}")
        return []

    peers = []
    now = time.time()
    lines = out.stdout.strip().splitlines()
    for line in lines[1:]:  # первая строка — сам интерфейс
        f = line.split("\t")
        if len(f) < 8:
            continue
        handshake = int(f[4])
        peers.append({
            "pubkey": f[0],
            "handshake_age": int(now - handshake) if handshake else None,
            "rx_bytes": int(f[5]),
            "tx_bytes": int(f[6]),
        })
    return peers


def bridge_check() -> dict:
    """TCP-проверка РУ-моста: жив ли и какой RTT."""
    host, _, port = BRIDGE_ADDR.partition(":")
    t0 = time.time()
    try:
        with socket.create_connection((host, int(port or 22)), timeout=4):
            return {"ok": True, "latency_ms": round((time.time() - t0) * 1000)}
    except OSError:
        return {"ok": False, "latency_ms": None}


def sample_vpn() -> None:
    """Срез VPN в SQLite — зовётся из общего 5-минутного сэмплера."""
    from tools import db

    peers = wg_dump()
    bridge = bridge_check()
    db.save_vpn_sample(
        peers=[{
            "pubkey": p["pubkey"],
            "rx_bytes": p["rx_bytes"],
            "tx_bytes": p["tx_bytes"],
            "online": p["handshake_age"] is not None and p["handshake_age"] < ONLINE_THRESHOLD_SEC,
        } for p in peers],
        bridge_ok=bridge["ok"],
        bridge_latency_ms=bridge["latency_ms"],
    )
    reality_sample()


def _delta_series(samples: list[dict]) -> list[dict]:
    """Кумулятивные счётчики → дельты между сэмплами (MB), кламп при ребуте WG."""
    by_ts: dict[str, dict] = {}
    prev: dict[str, tuple[int, int]] = {}
    for s in samples:  # samples отсортированы по ts
        ts = s["ts"]
        slot = by_ts.setdefault(ts, {"ts": ts, "rx_mb": 0.0, "tx_mb": 0.0, "online": 0})
        p = prev.get(s["pubkey"])
        if p is not None:
            drx = max(s["rx_bytes"] - p[0], 0)
            dtx = max(s["tx_bytes"] - p[1], 0)
            slot["rx_mb"] += drx / 1024 / 1024
            slot["tx_mb"] += dtx / 1024 / 1024
        slot["online"] += 1 if s["online"] else 0
        prev[s["pubkey"]] = (s["rx_bytes"], s["tx_bytes"])
    out = list(by_ts.values())
    for slot in out:
        slot["rx_mb"] = round(slot["rx_mb"], 2)
        slot["tx_mb"] = round(slot["tx_mb"], 2)
    return out


CLASH_API = os.getenv("MIRA_REALITY_CLASH_API", "http://127.0.0.1:9090")


def _clash_connections() -> dict[str, dict] | None:
    """Per-user активность Reality из sing-box clash_api (если включён).

    Возвращает {user_name: {rx, tx, online}} или None, если API недоступен
    (clash_api не настроен в engine.conf — тогда учёт деградирует до списка).
    """
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(f"{CLASH_API}/connections", timeout=2) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None

    agg: dict[str, dict] = {}
    for c in data.get("connections", []):
        user = (c.get("metadata") or {}).get("user")
        if not user:
            continue
        a = agg.setdefault(user, {"rx": 0, "tx": 0, "online": True})
        a["rx"] += int(c.get("download", 0))
        a["tx"] += int(c.get("upload", 0))
    return agg


def _reality_names() -> dict[str, str]:
    """{name: name} зарегистрированных Reality-юзеров (из vpn_peers.json)."""
    names = peer_names()
    return {v: v for k, v in names.items() if k.startswith("reality:")}


def reality_sample() -> None:
    """Срез clash_api в SQLite — зовётся из общего 5-минутного сэмплера.

    Пишем суммарный трафик активных сессий каждого зарегистрированного
    Reality-юзера. Юзеров без активных соединений пишем с нулём (онлайн=0),
    чтобы график показывал и простой.
    """
    from tools import db

    registered = _reality_names()
    if not registered:
        return
    conns = _clash_connections()
    if conns is None:
        return
    rows = []
    for name in registered:
        live = conns.get(name)
        rows.append({
            "name": name,
            "rx_bytes": live["rx"] if live else 0,
            "tx_bytes": live["tx"] if live else 0,
            "online": bool(live and live["online"]),
        })
    db.save_reality_sample(rows)


def reality_peers(hours: int = 24) -> list[dict]:
    """Reality-пользователи для экрана VPN: накопление за период + живой онлайн.

    Имена — из vpn_peers.json. Трафик за период — дельты clash-сэмплов из
    БД (clash считает по живым сессиям, поэтому это активность, не байт-в-байт
    кумулятив). Онлайн — из живого clash_api.
    """
    from tools import db

    registered = _reality_names()
    if not registered:
        return []

    conns = _clash_connections()
    samples = db.load_reality_samples(hours)

    # Накопление по юзеру: дельты между сэмплами, кламп при сбросе сессии.
    per_user: dict[str, dict] = {}
    prev: dict[str, tuple[int, int]] = {}
    for s in samples:
        st = per_user.setdefault(s["name"], {"rx": 0, "tx": 0, "online_samples": 0})
        p = prev.get(s["name"])
        if p is not None:
            st["rx"] += max(s["rx_bytes"] - p[0], 0)
            st["tx"] += max(s["tx_bytes"] - p[1], 0)
        st["online_samples"] += 1 if s["online"] else 0
        prev[s["name"]] = (s["rx_bytes"], s["tx_bytes"])

    out = []
    for name in sorted(registered):
        st = per_user.get(name)
        live = conns.get(name) if conns else None
        out.append({
            "name": name,
            "kind": "reality",
            "online": bool(live and live["online"]),
            "last_seen_min": None,
            "rx_mb": round(st["rx"] / 1024 / 1024, 1) if st else 0.0,
            "tx_mb": round(st["tx"] / 1024 / 1024, 1) if st else 0.0,
            "online_minutes": st["online_samples"] * 5 if st else 0,
        })
    return out


def _reality_delta_series(hours: int = 24) -> list[dict]:
    """Reality-трафик по 5-мин слотам (дельты сэмплов) — для общего графика."""
    from tools import db

    samples = db.load_reality_samples(hours)
    by_ts: dict[str, dict] = {}
    prev: dict[str, tuple[int, int]] = {}
    for s in samples:
        slot = by_ts.setdefault(s["ts"], {"ts": s["ts"], "rx_mb": 0.0, "tx_mb": 0.0})
        p = prev.get(s["name"])
        if p is not None:
            slot["rx_mb"] += max(s["rx_bytes"] - p[0], 0) / 1024 / 1024
            slot["tx_mb"] += max(s["tx_bytes"] - p[1], 0) / 1024 / 1024
        prev[s["name"]] = (s["rx_bytes"], s["tx_bytes"])
    for slot in by_ts.values():
        slot["rx_mb"] = round(slot["rx_mb"], 2)
        slot["tx_mb"] = round(slot["tx_mb"], 2)
    return list(by_ts.values())


def _traffic_series(hours: int, wg_samples: list[dict], wg_names: dict[str, str]) -> list[dict]:
    """Трафик по времени с разбивкой по устройствам — для stacked-графика.

    Каждый слот (минутный ts) → {имя: МБ за слот}. WG и Reality дельты,
    кламп при сбросе счётчиков. Имена WG берутся из peer_names по pubkey.
    """
    from tools import db

    slots: dict[str, dict[str, float]] = {}

    def _accumulate(samples, name_of):
        prev: dict[str, tuple[int, int]] = {}
        for s in samples:
            key = s["ts"][:16]
            name = name_of(s)
            p = prev.get(s["name"] if "name" in s else s["pubkey"])
            ident = s.get("name") or s.get("pubkey")
            if p is not None:
                mb = (max(s["rx_bytes"] - p[0], 0) + max(s["tx_bytes"] - p[1], 0)) / 1024 / 1024
                if mb:
                    slot = slots.setdefault(key, {})
                    slot[name] = round(slot.get(name, 0.0) + mb, 2)
            prev[ident] = (s["rx_bytes"], s["tx_bytes"])

    _accumulate(wg_samples, lambda s: wg_names.get(s["pubkey"]) or f"{s['pubkey'][:8]}…")
    _accumulate(db.load_reality_samples(hours), lambda s: s["name"])

    return [{"ts": ts, "users": slots[ts]} for ts in sorted(slots)]


def vpn_stats(hours: int = 24) -> dict:
    """Сводка для экрана VPN: текущее состояние + агрегаты за период."""
    from tools import db

    live = {p["pubkey"]: p for p in wg_dump()}
    bridge = bridge_check()
    samples = db.load_vpn_peer_samples(hours)
    bridge_hist = db.load_vpn_bridge_samples(hours)

    # Агрегаты по пирам за период
    per_peer: dict[str, dict] = {}
    for s in samples:
        st = per_peer.setdefault(s["pubkey"], {
            "first_rx": s["rx_bytes"], "first_tx": s["tx_bytes"],
            "last_rx": s["rx_bytes"], "last_tx": s["tx_bytes"],
            "online_samples": 0, "resets_rx": 0, "resets_tx": 0,
        })
        # Ребут WG обнуляет счётчики — копим прошлый максимум
        if s["rx_bytes"] < st["last_rx"]:
            st["resets_rx"] += st["last_rx"] - st["first_rx"]
            st["first_rx"] = 0
        if s["tx_bytes"] < st["last_tx"]:
            st["resets_tx"] += st["last_tx"] - st["first_tx"]
            st["first_tx"] = 0
        st["last_rx"], st["last_tx"] = s["rx_bytes"], s["tx_bytes"]
        st["online_samples"] += 1 if s["online"] else 0

    names = peer_names()
    pubkeys = set(per_peer) | set(live)
    peers_out = []
    for pk in sorted(pubkeys, key=lambda k: names.get(k, "я" + k)):
        st = per_peer.get(pk)
        lv = live.get(pk)
        age = lv["handshake_age"] if lv else None
        peers_out.append({
            "name": names.get(pk) or f"{pk[:8]}…",
            "kind": "wireguard",
            "online": age is not None and age < ONLINE_THRESHOLD_SEC,
            "last_seen_min": (age // 60) if age is not None else None,
            "rx_mb": round((st["last_rx"] - st["first_rx"] + st["resets_rx"]) / 1024 / 1024, 1) if st else 0.0,
            "tx_mb": round((st["last_tx"] - st["first_tx"] + st["resets_tx"]) / 1024 / 1024, 1) if st else 0.0,
            "online_minutes": st["online_samples"] * 5 if st else 0,
        })

    peers_out.extend(reality_peers(hours))

    # Общий трафик по времени = WG + Reality, слитые по минутному ts
    # (оба сэмплятся в одном проходе, но с разными миллисекундами).
    combined: dict[str, dict] = {}
    for pt in _delta_series(samples) + _reality_delta_series(hours):
        key = pt["ts"][:16]
        slot = combined.setdefault(key, {"ts": pt["ts"], "rx_mb": 0.0, "tx_mb": 0.0, "online": 0})
        slot["rx_mb"] = round(slot["rx_mb"] + pt["rx_mb"], 2)
        slot["tx_mb"] = round(slot["tx_mb"] + pt["tx_mb"], 2)
        slot["online"] = max(slot["online"], pt.get("online", 0))
    points = [combined[k] for k in sorted(combined)]

    return {
        "bridge_ok": bridge["ok"],
        "bridge_latency_ms": bridge["latency_ms"],
        "wg_up": bool(live),
        "peers_online": sum(1 for p in peers_out if p["online"]),
        "peers": peers_out,
        "points": points,
        "traffic_series": _traffic_series(hours, samples, names),
        "bridge_points": [
            {"ts": b["ts"], "ok": bool(b["ok"]), "latency_ms": b["latency_ms"]}
            for b in bridge_hist
        ],
    }
