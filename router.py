"""
router.py — классификатор задач.

Один дешёвый вызов API определяет тип запроса пользователя.
Результат используется agent.py чтобы решить: отвечать самостоятельно
или передать задачу Конклаву.

Метки:
    "chat"    — разговор, вопрос, мнение, пояснение
    "files"   — работа с файлами в workspace пользователя
    "code"    — написание, проверка, исправление кода
    "complex" — многошаговая задача: анализ, исследование, проект

Намеренно дёшев: маленький промпт, temperature=0, max_tokens=5.
"""

import logging
import providers as _providers

logger = logging.getLogger("Ouroborus")

LABELS = {"chat", "files", "code", "complex"}

_PROMPT = """\
Classify the user message into exactly one category.
Reply with ONE word only — the category label.

Categories:
- chat    : conversation, questions, explanations, opinions
- files   : reading, writing, listing files in the workspace
- code    : writing, reviewing, fixing, explaining code
- complex : multi-step task requiring planning or research

User message: {message}

Label:"""


def classify(message: str, model_chain: list[dict]) -> str:
    """
    Возвращает одну из меток: "chat" | "files" | "code" | "complex".
    При любой ошибке возвращает "chat" — безопасный fallback.

    Использует model_chain с temperature=0 для детерминированности.
    Обрезает входное сообщение до 400 символов чтобы держать prompt маленьким.
    """
    if not model_chain:
        return "chat"

    cheap_chain = [{**e, "temperature": 0.0} for e in model_chain]

    try:
        response = _providers.call(
            cheap_chain,
            messages=[{
                "role": "user",
                "content": _PROMPT.format(message=message[:400]),
            }],
            max_tokens=5,
        )
        raw = response.choices[0].message.content.strip().lower()

        # Модель может добавить знаки препинания или лишние слова
        label = raw.split()[0].rstrip(".,;:") if raw else "chat"

        if label not in LABELS:
            logger.warning(f"router: неизвестная метка '{label}', fallback → chat")
            return "chat"

        logger.info(f"router: {label!r} ← '{message[:60]}...'")
        return label

    except Exception as e:
        logger.warning(f"router: ошибка классификации ({e}), fallback → chat")
        return "chat"
