"""
conclave.py — оркестратор многоагентного Конклава.

Конклав работает за кулисами. Пользователь всегда говорит только с Альфой.
Conclave принимает задачу, прогоняет её через цепочку специалистов и
возвращает готовый результат — Альфа затем оформляет его своим голосом.

Архитектура:
    Conclave напрямую использует providers.call() без класса Agent.
    Это исключает circular import (agent.py = __main__, не module).
    Каждый специалист — JSON-конфиг в agents/{name}.json.

Методы:
    run(name, task)              — одиночный запуск специалиста
    run_with_qa(task, executor)  — цикл executor → editor → critic

Защиты от зацикливания (run_with_qa):
    1. Максимум 3 итерации — после третьей возвращаем лучший результат.
    2. Critic ставит оценку 0–10. Принимаем при ≥ PASS_SCORE (7).
    3. Оценка не растёт 2 итерации подряд — стоп.
    4. Heartbeat: статус после каждой итерации.
    5. should_stop: флаг для /stop и KeyboardInterrupt.
"""

import os
import re
import json
import logging
import providers as _providers

logger = logging.getLogger("Ouroborus")

AGENTS_DIR   = "agents"
MAX_ITER     = 3      # максимум итераций в run_with_qa
PASS_SCORE   = 7      # оценка critic при которой принимаем результат


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _load_config(name: str) -> dict:
    """Загружает конфиг агента из agents/{name}.json."""
    path = os.path.join(AGENTS_DIR, f"{name}.json")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Конфиг агента не найден: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _call(config: dict, messages: list) -> str:
    """
    Вызывает модель из конфига агента через providers.call().
    Возвращает текстовый ответ.
    """
    response = _providers.call(
        config["model_chain"],
        messages,
        max_tokens=config.get("max_tokens", 2048),
    )
    return response.choices[0].message.content or ""


def _parse_score(text: str) -> int:
    """
    Извлекает оценку 0–10 из ответа critic.

    Форматы которые понимаем:
        "OK: 8"      → 8
        "SCORE: 6"   → 6
        любое число  → берём первое вхождение
    """
    upper = text.upper()

    m = re.search(r"OK\s*:\s*(\d+)", upper)
    if m:
        return min(10, max(0, int(m.group(1))))

    m = re.search(r"SCORE\s*:\s*(\d+)", upper)
    if m:
        return min(10, max(0, int(m.group(1))))

    # Ищем изолированное число 0–10
    for match in re.finditer(r"\b(10|[0-9])\b", upper):
        return min(10, max(0, int(match.group(1))))

    return 5  # нейтральное значение при непонятном ответе


# ---------------------------------------------------------------------------
# Класс Conclave
# ---------------------------------------------------------------------------

class Conclave:
    """
    Оркестратор Конклава.

    Параметры при инициализации:
        system_prompt — системный промпт Альфы (для контекста при финальном
                        представлении результата; специалисты имеют свои промпты).

    Флаги:
        should_stop — выставляется командой /stop, прерывает цикл run_with_qa
                      между итерациями (не во время API-вызова).
    """

    def __init__(self, system_prompt: str = ""):
        self.system_prompt = system_prompt
        self.should_stop   = False

    # ------------------------------------------------------------------
    # Публичные методы
    # ------------------------------------------------------------------

    def run(self, agent_name: str, task: str, context: str = "") -> str:
        """
        Запускает одного специалиста с задачей.

        agent_name — имя файла без .json в папке agents/
        task       — что нужно сделать
        context    — дополнительный контекст (предыдущая версия, обратная связь)

        Возвращает текстовый ответ специалиста.
        """
        config = _load_config(agent_name)
        system = config.get("system_prompt", "")

        content = task
        if context:
            content = f"{task}\n\n---\nКонтекст / предыдущая версия:\n{context}"

        messages = [
            {"role": "system", "content": system},
            {"role": "user",   "content": content},
        ]

        result = _call(config, messages)
        logger.info(f"Conclave.run: {agent_name} завершил ({len(result)} символов)")
        return result

    def run_with_qa(self, task: str, executor_name: str = "coder") -> str:
        """
        Цикл качества: executor → editor → critic (до MAX_ITER раз).

        Возвращает лучший результат даже если critic так и не поставил ≥7.
        Лучший = с наибольшей оценкой critic за все итерации.
        """
        best_result = ""
        best_score  = -1
        prev_score  = -1
        stagnation  = 0

        for iteration in range(1, MAX_ITER + 1):

            if self.should_stop:
                print("[Конклав] Остановлен.")
                logger.info("Conclave: остановлен флагом should_stop")
                break

            print(f"\n[Конклав] Итерация {iteration}/{MAX_ITER} — {executor_name}...")

            # --- Executor ---
            exec_ctx = (
                f"Предыдущая версия (улучши её):\n{best_result}"
                if best_result else ""
            )
            try:
                result = self.run(executor_name, task, exec_ctx)
            except Exception as e:
                logger.error(f"Conclave: {executor_name} упал ({e})")
                if best_result:
                    break   # вернём лучшее что есть
                return f"[Ошибка: специалист '{executor_name}' недоступен — {e}]"

            if self.should_stop:
                break

            # --- Editor ---
            print(f"[Конклав] Итерация {iteration}/{MAX_ITER} — editor...")
            try:
                result = self.run(
                    "editor",
                    "Улучши текст или код: убери лишнее, повысь ясность, не меняй смысл.",
                    result,
                )
            except Exception as e:
                logger.warning(f"Conclave: editor упал ({e}), продолжаю без редактуры")

            if self.should_stop:
                break

            # --- Critic ---
            print(f"[Конклав] Итерация {iteration}/{MAX_ITER} — critic...")
            score, feedback = self._run_critic(task, result)
            print(f"[Конклав] Оценка: {score}/10")

            if score > best_score:
                best_score  = score
                best_result = result

            # Принимаем если достаточно хорошо
            if score >= PASS_SCORE:
                print(f"[Конклав] Принято (оценка {score}/10).")
                logger.info(f"Conclave: принято на итерации {iteration}, score={score}")
                break

            # Стагнация — оценка не растёт
            if score <= prev_score:
                stagnation += 1
                if stagnation >= 2:
                    print(f"[Конклав] Оценка не растёт. Завершаю с лучшим результатом.")
                    logger.info(f"Conclave: стагнация {stagnation}, best_score={best_score}")
                    break
            else:
                stagnation = 0

            prev_score = score

            if iteration < MAX_ITER and not self.should_stop:
                print(f"[Конклав] Продолжаю. Критика: {feedback[:120]}...")

        if not best_result:
            best_result = "[Конклав не смог получить результат]"

        logger.info(f"Conclave.run_with_qa завершён. best_score={best_score}")
        return best_result

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    def _run_critic(self, task: str, result: str) -> tuple[int, str]:
        """
        Запускает critic и парсит оценку.
        Возвращает (score: 0–10, feedback: str).
        При ошибке возвращает нейтральный score=5.
        """
        try:
            config = _load_config("critic")
            prompt = (
                f"Задача:\n{task}\n\n"
                f"Результат:\n{result}\n\n"
                "Оцени результат по шкале 0–10.\n"
                "Если оценка ≥ 7 — напиши: OK: <число>\n"
                "Если оценка < 7 — напиши список конкретных проблем, затем: SCORE: <число>"
            )
            messages = [
                {"role": "system", "content": config.get("system_prompt", "")},
                {"role": "user",   "content": prompt},
            ]
            feedback = _call(config, messages)
            score    = _parse_score(feedback)
            return score, feedback

        except Exception as e:
            logger.warning(f"Conclave: critic упал ({e}), score=5")
            return 5, str(e)
