"""tools/v2ray_stats.py — per-user трафик Reality через sing-box v2ray_api (gRPC).

sing-box с тегом with_v2ray_api отдаёт кумулятивные счётчики на каждого
пользователя inbound: «user>>>ИМЯ>>>traffic>>>uplink» и «…downlink».
В отличие от clash_api, здесь есть имя пользователя — можно разделять
трафик по людям. Счётчики кумулятивные (с момента старта sing-box),
поэтому считаются дельтами, как у WireGuard.
"""

import logging
import os

logger = logging.getLogger("Ouroboros")

V2RAY_API = os.getenv("MIRA_REALITY_V2RAY_API", "127.0.0.1:8081")


def query_user_traffic() -> dict[str, dict] | None:
    """{имя: {"downlink": байт, "uplink": байт}} или None, если API недоступен.

    Кумулятивные счётчики с момента старта sing-box.
    """
    try:
        import grpc
        from tools.v2ray_proto import stats_pb2, stats_pb2_grpc
    except Exception as e:
        logger.warning(f"v2ray_stats: grpc/stubs недоступны: {e}")
        return None

    try:
        with grpc.insecure_channel(V2RAY_API) as ch:
            stub = stats_pb2_grpc.StatsServiceStub(ch)
            resp = stub.QueryStats(
                stats_pb2.QueryStatsRequest(pattern="user>>>", reset=False),
                timeout=3,
            )
    except Exception as e:
        logger.warning(f"v2ray_stats: запрос упал: {e}")
        return None

    out: dict[str, dict] = {}
    for s in resp.stat:
        # name = "user>>>Admin>>>traffic>>>uplink"
        parts = s.name.split(">>>")
        if len(parts) == 4 and parts[0] == "user" and parts[2] == "traffic":
            name, direction = parts[1], parts[3]
            u = out.setdefault(name, {"downlink": 0, "uplink": 0})
            if direction in ("uplink", "downlink"):
                u[direction] = int(s.value)
    return out
