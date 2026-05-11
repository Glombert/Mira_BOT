"""
tools/semantic_memory.py — векторная память на ChromaDB.

Зачем:
    MAX_HISTORY=40 и текстовое резюме хорошо работают для линейной
    последовательности диалога. Но Мира не помнит "по смыслу" — если
    мы обсуждали что-то месяц назад, в текущей сессии этого нет.

Что делает:
    - index_message(user_id, role, text, ts) — записывает сообщение в векторную базу
    - search(user_id, query, top_k=5) — ищет релевантные прошлые сообщения по смыслу
    - delete_user(user_id) — удаляет все векторы пользователя (для /forget)
    - count(user_id) — сколько сообщений проиндексировано

Хранение:
    memory/chroma/ — SQLite + onnxruntime. Один сборник, фильтр по user_id.
    Эмбеддинги — встроенные ChromaDB (MiniLM-L6-v2 через onnxruntime, бесплатно).

Безопасность:
    Тексты хранятся в plaintext в ChromaDB. Это допустимо — VPS уже
    защищён SSH-ключом, а оригинал в memory/sessions/ зашифрован
    Fernet. Векторная база — только для быстрого поиска.
"""

import os
import logging
import threading
from datetime import datetime

logger = logging.getLogger("Ouroborus")

CHROMA_DIR      = os.path.join("memory", "chroma")
COLLECTION_NAME = "messages"

# Минимальная длина текста для индексации — короткие "ок" / "ага" не нужны
MIN_LEN = 12

# Максимум символов на сообщение — длинные ответы обрезаем для поиска
MAX_LEN = 2000

_client     = None
_collection = None
_lock       = threading.Lock()
_disabled   = False  # ставим True если chromadb сломан — graceful degradation


def _init() -> bool:
    """Lazy-init клиента и сборника. Возвращает True если готово."""
    global _client, _collection, _disabled
    if _disabled:
        return False
    if _collection is not None:
        return True

    with _lock:
        if _collection is not None:
            return True
        try:
            import chromadb
            os.makedirs(CHROMA_DIR, exist_ok=True)
            _client = chromadb.PersistentClient(path=CHROMA_DIR)
            _collection = _client.get_or_create_collection(
                name=COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(f"semantic_memory: ChromaDB готова, collection={COLLECTION_NAME}")
            return True
        except ImportError:
            logger.warning("semantic_memory: chromadb не установлен — семантическая память отключена")
            _disabled = True
            return False
        except Exception as e:
            logger.error(f"semantic_memory: не удалось инициализировать ChromaDB — {e}")
            _disabled = True
            return False


def is_enabled() -> bool:
    """Доступна ли семантическая память."""
    return _init()


def index_message(user_id: str, role: str, text: str, ts: str | None = None) -> bool:
    """
    Записывает сообщение в векторную базу.

    user_id — ID пользователя (для фильтрации поиска)
    role    — "user" или "assistant"
    text    — содержимое
    ts      — ISO timestamp (если None — текущее время)

    Возвращает True если проиндексировано, False если пропущено или ошибка.
    """
    if not _init():
        return False
    if not text or not isinstance(text, str):
        return False
    text = text.strip()
    if len(text) < MIN_LEN:
        return False
    if len(text) > MAX_LEN:
        text = text[:MAX_LEN] + "…"

    ts = ts or datetime.now().isoformat()
    # ID = user_id + timestamp + первые 8 символов хеша — стабилен и уникален
    import hashlib
    h = hashlib.sha256(f"{user_id}:{ts}:{text[:200]}".encode()).hexdigest()[:8]
    doc_id = f"{user_id}_{ts}_{h}"

    try:
        _collection.add(
            ids=[doc_id],
            documents=[text],
            metadatas=[{"user_id": user_id, "role": role, "ts": ts}],
        )
        return True
    except Exception as e:
        # Дубликат ID — это норм, просто пропускаем
        if "ID" in str(e) and "exists" in str(e).lower():
            return False
        logger.warning(f"semantic_memory.index_message: {e}")
        return False


def search(user_id: str, query: str, top_k: int = 5,
           max_distance: float = 0.95) -> list[dict]:
    """
    Ищет релевантные сообщения пользователя по смыслу.

    Возвращает список словарей: {text, role, ts, distance}
    distance — расстояние косинусной близости (ниже = ближе).
    max_distance отсекает шум.
    """
    if not _init():
        return []
    if not query or len(query.strip()) < 3:
        return []

    try:
        result = _collection.query(
            query_texts=[query.strip()],
            n_results=top_k,
            where={"user_id": user_id},
        )
    except Exception as e:
        logger.warning(f"semantic_memory.search: {e}")
        return []

    docs      = (result.get("documents")  or [[]])[0]
    metas     = (result.get("metadatas")  or [[]])[0]
    distances = (result.get("distances")  or [[]])[0]

    out = []
    for doc, meta, dist in zip(docs, metas, distances):
        if dist > max_distance:
            continue
        out.append({
            "text":     doc,
            "role":     (meta or {}).get("role", "unknown"),
            "ts":       (meta or {}).get("ts", ""),
            "distance": float(dist),
        })
    return out


def delete_user(user_id: str) -> int:
    """Удаляет все векторы пользователя. Возвращает сколько удалено."""
    if not _init():
        return 0
    try:
        # Сначала найдём сколько было
        existing = _collection.get(where={"user_id": user_id})
        ids = existing.get("ids", []) if existing else []
        if not ids:
            return 0
        _collection.delete(ids=ids)
        logger.info(f"semantic_memory: удалено {len(ids)} векторов пользователя {user_id}")
        return len(ids)
    except Exception as e:
        logger.warning(f"semantic_memory.delete_user: {e}")
        return 0


def count(user_id: str | None = None) -> int:
    """Сколько сообщений проиндексировано. Без user_id — всего."""
    if not _init():
        return 0
    try:
        if user_id:
            r = _collection.get(where={"user_id": user_id}, include=[])
        else:
            r = _collection.get(include=[])
        return len(r.get("ids", []))
    except Exception as e:
        logger.warning(f"semantic_memory.count: {e}")
        return 0


def format_for_prompt(matches: list[dict]) -> str:
    """Форматирует результат search() в текстовый блок для системного промпта."""
    if not matches:
        return ""
    lines = []
    for m in matches:
        role = "пользователь" if m["role"] == "user" else "ты"
        date = m["ts"][:10] if m["ts"] else ""
        lines.append(f"— [{date}] {role}: {m['text']}")
    return "Из прошлых разговоров вспомнила:\n" + "\n".join(lines)
