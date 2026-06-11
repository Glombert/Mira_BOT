"""Тесты tools/vpn_tools — учёт WireGuard-пиров и проверка моста."""

import time

import pytest  # noqa: F401 — fixtures

from tools import vpn_tools as vt

WG_DUMP = (
    "PRIVKEY\tSERVERPUB\t51820\toff\n"
    "PEER_A_KEY\t(none)\t5.42.98.236:44544\t10.66.66.2/32\t{hs}\t1000000\t5000000\toff\n"
    "PEER_B_KEY\t(none)\t(none)\t10.66.66.3/32\t0\t0\t0\toff\n"
)

class _Proc:
    def __init__(self, stdout):
        self.stdout = stdout
        self.returncode = 0
        self.stderr = ""

def test_wg_dump_parses_peers(monkeypatch):
    hs = int(time.time()) - 60
    monkeypatch.setattr(vt.subprocess, "run", lambda *a, **k: _Proc(WG_DUMP.format(hs=hs)))
    peers = vt.wg_dump()
    assert len(peers) == 2
    a, b = peers
    assert a["pubkey"] == "PEER_A_KEY" and 55 <= a["handshake_age"] <= 65
    assert a["rx_bytes"] == 1000000 and a["tx_bytes"] == 5000000
    assert b["handshake_age"] is None  # хендшейка не было никогда

def test_delta_series_clamps_reset():
    mb = 1024 * 1024
    samples = [
        {"ts": "t1", "pubkey": "A", "rx_bytes": 10 * mb, "tx_bytes": 0, "online": 1},
        {"ts": "t2", "pubkey": "A", "rx_bytes": 15 * mb, "tx_bytes": 0, "online": 1},
        {"ts": "t3", "pubkey": "A", "rx_bytes": 2 * mb, "tx_bytes": 0, "online": 0},  # ребут WG
    ]
    pts = vt._delta_series(samples)
    assert [p["rx_mb"] for p in pts] == [0.0, 5.0, 0.0]  # отрицательная дельта = 0
    assert [p["online"] for p in pts] == [1, 1, 0]

def test_vpn_stats_aggregates(isolated_cwd, monkeypatch):
    from tools import db
    mb = 1024 * 1024
    monkeypatch.setattr(vt, "wg_dump", lambda: [
        {"pubkey": "A", "handshake_age": 30, "rx_bytes": 30 * mb, "tx_bytes": 60 * mb},
    ])
    monkeypatch.setattr(vt, "bridge_check", lambda: {"ok": True, "latency_ms": 12})
    monkeypatch.setattr(vt, "peer_names", lambda: {"A": "Кенетик"})

    db.save_vpn_sample([{"pubkey": "A", "rx_bytes": 10 * mb, "tx_bytes": 20 * mb, "online": True}], True, 10)
    db.save_vpn_sample([{"pubkey": "A", "rx_bytes": 30 * mb, "tx_bytes": 60 * mb, "online": True}], True, 14)

    v = vt.vpn_stats(24)
    assert v["bridge_ok"] and v["wg_up"] and v["peers_online"] == 1
    peer = v["peers"][0]
    assert peer["name"] == "Кенетик" and peer["online"] and peer["kind"] == "wireguard"
    assert peer["rx_mb"] == 20.0 and peer["tx_mb"] == 40.0
    assert peer["online_minutes"] == 10
    assert len(v["points"]) == 2 and len(v["bridge_points"]) == 2


def test_reality_peers_listed_without_clash(monkeypatch):
    monkeypatch.setattr(vt, "peer_names", lambda: {
        "reality:uuid-1": "admin (Reality)",
        "WGKEY": "Кенетик",
    })
    monkeypatch.setattr(vt, "_clash_connections", lambda: None)  # clash_api выключен
    peers = vt.reality_peers()
    assert len(peers) == 1
    assert peers[0]["name"] == "admin (Reality)" and peers[0]["kind"] == "reality"
    assert peers[0]["online"] is False and peers[0]["last_seen_min"] is None


def test_reality_peers_online_via_clash(monkeypatch):
    mb = 1024 * 1024
    monkeypatch.setattr(vt, "peer_names", lambda: {"reality:uuid-1": "admin"})
    monkeypatch.setattr(vt, "_clash_connections",
                        lambda: {"admin": {"rx": 5 * mb, "tx": 2 * mb, "online": True}})
    peers = vt.reality_peers()
    assert peers[0]["online"] and peers[0]["rx_mb"] == 5.0 and peers[0]["tx_mb"] == 2.0

def test_bridge_check_down(monkeypatch):
    monkeypatch.setattr(vt, "BRIDGE_ADDR", "127.0.0.1:1")  # закрытый порт
    r = vt.bridge_check()
    assert r["ok"] is False and r["latency_ms"] is None
