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
import time
import random
import logging
import concurrent.futures
import providers as _providers

logger = logging.getLogger("Ouroboros")

AGENTS_DIR   = "agents"
MAX_ITER     = 3      # максимум итераций в run_with_qa
PASS_SCORE   = 7      # оценка critic при которой принимаем результат

_AGENT_NAMES = {
    "coder":            "Кодер",
    "editor":           "Редактор",
    "critic":           "Критик",
    "planner":          "Планировщик",
    "scout":            "Разведчик",
    "reviewer":         "Ревьюер",
    "excel_specialist": "Excel-специалист",
    "artist":           "Художник",
}

# Прогресс-фразы в голосе Миры. random.choice — чтобы не повторялись.
_PHRASES = {
    "executor_start": {
        "coder":            ["Дёрнула Кодера, секунду", "Скинула Кодеру, ждём", "Кодер взялся за это"],
        "scout":            ["Так, копаю в инете", "Слушай, дай гляну в сети", "Сейчас, поищу"],
        "planner":          ["Сейчас Планировщик разложит по полочкам", "Дам Планировщику разобраться"],
        "excel_specialist": ["Excel-спец возьмётся", "Кидаю Excel-специалисту"],
        "artist":           ["Художник берётся за кисть", "Передаю Художнику, сейчас нарисует", "Художник уже рисует"],
        "default":          ["Так, иду к специалистам", "Сейчас, обработаю"],
    },
    "editor":  ["Редактор причёсывает", "Сейчас доведу до ума", "Чуть подправлю"],
    "critic":  ["Гляну, что получилось", "Сейчас проверю качество", "Так, оценю"],
    "accept":  ["Готово, сейчас расскажу", "Ага, есть! Делюсь", "Норм получилось, держи"],
    "stagnation": ["Ладно, что есть — то есть", "Окей, беру лучший вариант"],
    "retry":   ["Не доделала, ещё разок", "Хм, надо подкрутить", "Так, попробую ещё"],
    "stopped": ["Окей, остановилась. Что успела — отдам"],
}


def _pick(category: str, key: str | None = None) -> str:
    """Выбирает случайную фразу из заданной категории."""
    pool = _PHRASES.get(category, {})
    if isinstance(pool, dict):
        options = pool.get(key, pool.get("default", []))
    else:
        options = pool
    return random.choice(options) if options else ""


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

    # Fallback (критик не дал OK:/SCORE:): берём ПОСЛЕДНЕЕ число, а не первое —
    # в «нашёл 3 проблемы, ставлю 8» оценка идёт в конце, а не в начале.
    nums = re.findall(r"\b(10|[0-9])\b", upper)
    if nums:
        return min(10, max(0, int(nums[-1])))

    return 5  # нейтральное значение при непонятном ответе


_CODE_FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)


def _extract_python(text: str) -> str | None:
    """Достаёт Python-код из ```-фенсов; если фенсов нет, но текст похож на
    цельный код (начинается с import/def/class/@) — берём как есть. Иначе None."""
    blocks = _CODE_FENCE.findall(text or "")
    if blocks:
        return "\n\n".join(b.strip() for b in blocks)
    stripped = (text or "").strip()
    if re.match(r"^(import |from |def |class |async def |@)", stripped):
        return stripped
    return None


# ---------------------------------------------------------------------------
# Класс Conclave
# ---------------------------------------------------------------------------

class Conclave:
    """
    Оркестратор Конклава.

    Параметры:
        system_prompt    — промпт Альфы (для контекста при представлении результата)
        user_id          — ID пользователя, нужен для execute_tool (workspace isolation)
        profile          — профиль пользователя, нужен для проверки прав на инструменты
        tool_schemas     — список JSON-схем инструментов (TOOL_SCHEMAS из agent.py)
        execute_tool_fn  — функция вызова инструментов (execute_tool из agent.py)

    Флаг should_stop прерывает run_with_qa между итерациями (не во время API-вызова).
    """

    def __init__(self, system_prompt: str = "", user_id: str = "",
                 profile=None, tool_schemas: list | None = None,
                 execute_tool_fn=None):
        self.system_prompt   = system_prompt
        self.user_id         = user_id
        self.profile         = profile
        self.tool_schemas    = tool_schemas or []
        self.execute_tool_fn = execute_tool_fn
        self.should_stop     = False
        self.on_progress     = None  # callable(str) | None — heartbeat для Telegram

    def _progress(self, text: str) -> None:
        """Отправляет прогресс-сообщение через on_progress callback (если задан) и в лог."""
        logger.info(f"Conclave progress: {text}")
        if callable(self.on_progress):
            try:
                self.on_progress(f"💭 {text}")
            except Exception as e:
                logger.warning(f"on_progress callback error: {e}")

    # ------------------------------------------------------------------
    # Публичные методы
    # ------------------------------------------------------------------

    def run(self, agent_name: str, task: str, context: str = "") -> str:
        """
        Запускает одного специалиста с задачей.

        Если агент имеет allowed_tools и Conclave инициализирован с инструментами —
        агент получает доступ к ним и может реально создавать файлы, запускать код.
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

        allowed = config.get("allowed_tools", [])
        if allowed and self.tool_schemas and self.execute_tool_fn:
            result = self._call_agentic(config, messages, allowed)
        else:
            result = _call(config, messages)

        logger.info(f"Conclave.run: {agent_name} завершил ({len(result)} символов)")
        return result

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    def _call_agentic(self, config: dict, messages: list, allowed_tools: list) -> str:
        """
        Вызов агента с поддержкой tool_calls.

        Поддерживает два вида моделей в model_chain:
          - native_search=true (Perplexity): встроенный поиск, tools не нужны.
            Вызываются первыми, без схем инструментов.
          - обычные (DeepSeek, Claude): вызываются с tool_calls если schemas непусты.

        Фильтрует TOOL_SCHEMAS по allowed_tools агента И правам профиля пользователя.
        """
        # Фильтруем инструменты: агент + профиль пользователя (PRINCIPLES §3)
        allowed_set = set(allowed_tools)
        schemas = [
            s for s in self.tool_schemas
            if s["function"]["name"] in allowed_set
            and (self.profile is None or self.profile.can_use(s["function"]["name"]))
        ]

        full_chain  = config.get("model_chain", [])
        # Модели с встроенным поиском (Perplexity) — вызываем без tools
        native_chain = [e for e in full_chain if e.get("native_search")]
        # Обычные модели — вызываем с tools
        tools_chain  = [e for e in full_chain if not e.get("native_search")]

        # Определяем максимальное количество раундов инструментов
        max_tool_rounds = self.profile.max_tool_rounds if self.profile else 30

        # --- Сначала пробуем native-search модели ---
        if native_chain:
            try:
                response = _providers.call(
                    native_chain, messages,
                    max_tokens=config.get("max_tokens", 2048),
                )
                content = response.choices[0].message.content or ""
                if content:
                    logger.info(f"Conclave: native search ответил ({len(content)} символов)")
                    return content
            except Exception as e:
                logger.warning(f"Conclave: native search упал ({e}), переключаюсь на инструменты")

        # --- Fallback: tools-capable модели ---
        if not schemas or not tools_chain:
            fallback_cfg = {**config, "model_chain": tools_chain or full_chain}
            return _call(fallback_cfg, messages)

        tool_cfg = {**config, "model_chain": tools_chain}

        for _ in range(max_tool_rounds):
            response = _providers.call(
                tool_cfg["model_chain"],
                messages,
                max_tokens=tool_cfg.get("max_tokens", 2048),
                tools=schemas,
                tool_choice="auto",
            )
            msg = response.choices[0].message

            # Нет tool_calls — возвращаем текст
            if not msg.tool_calls:
                return msg.content or ""

            # Конвертируем в dict (иначе trim_history сломается)
            messages.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })

            for tc in msg.tool_calls:
                tool_name = tc.function.name
                tool_args = json.loads(tc.function.arguments)

                logger.info(f"Conclave tool: [{config.get('name', 'unknown')}] → {tool_name}({tool_args})")

                result = self.execute_tool_fn(tool_name, tool_args, self.user_id)

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })

        logger.warning(f"Conclave: превышен лимит вызовов инструментов ({max_tool_rounds}) для {config.get('name', 'unknown')}")
        return "[Превышен лимит вызовов инструментов]"

    def run_with_qa(self, task: str, executor_name: str = "coder",
                    skip_editor: bool = False, parallel_scout: bool = False) -> str:
        """
        Цикл качества: executor → editor → critic (до MAX_ITER раз).

        Возвращает лучший результат даже если critic так и не поставил ≥7.
        Лучший = с наибольшей оценкой critic за все итерации.

        skip_editor    — не вызывать Редактора (для простых задач: search, chat)
        parallel_scout — на первой итерации запустить Разведчика параллельно с исполнителем
        """
        best_result = ""
        best_score  = -1
        prev_score  = -1
        stagnation  = 0
        last_feedback = ""  # замечания критика прошлой итерации → следующему executor'у
        iteration   = 0   # на случай MAX_ITER=0 (иначе UnboundLocalError в финальном логе)
        t_start     = time.time()

        for iteration in range(1, MAX_ITER + 1):

            if self.should_stop:
                self._progress(_pick("stopped"))
                logger.info("Conclave: остановлен флагом should_stop")
                break

            # Объявляем только первый запуск executor — остальные итерации видны через "retry"
            if iteration == 1:
                self._progress(_pick("executor_start", executor_name))

            # --- Executor (+ параллельный scout на первой итерации) ---
            exec_ctx = (
                f"Предыдущая версия (улучши её):\n{best_result}"
                if best_result else ""
            )
            # Критик уже оценивал прошлую версию — даём executor'у его замечания,
            # иначе он переписывает вслепую и цикл качества буксует.
            if last_feedback:
                exec_ctx += f"\n\nЗамечания критика к прошлой версии (учти их):\n{last_feedback}"

            if parallel_scout and iteration == 1 and executor_name != "scout":
                # Запускаем Разведчика и основного исполнителя параллельно
                self._progress(_pick("executor_start", "scout"))
                with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
                    scout_fut = pool.submit(self.run, "scout", task, "")
                    exec_fut  = pool.submit(self.run, executor_name, task, exec_ctx)
                    scout_res = scout_fut.result()
                    exec_res  = exec_fut.result()
                result = (
                    f"Результаты исследования:\n{scout_res}\n\n"
                    f"Результат выполнения:\n{exec_res}"
                )
                logger.info(f"Conclave: parallel scout+{executor_name} завершены")
            else:
                try:
                    result = self.run(executor_name, task, exec_ctx)
                except Exception as e:
                    logger.error(f"Conclave: {executor_name} упал ({e})")
                    if best_result:
                        break
                    return f"[Ошибка: специалист '{executor_name}' недоступен — {e}]"

            if self.should_stop:
                self._progress(_pick("stopped"))
                break

            # --- Editor (пропускаем для простых задач) ---
            if not skip_editor:
                try:
                    result = self.run(
                        "editor",
                        f"Исходная задача:\n{task}\n\n"
                        "Улучши результат ПОД ЭТУ ЗАДАЧУ: убери лишнее, повысь ясность, "
                        "не отклоняйся от требований и НЕ удаляй нужную логику/проверки ошибок.",
                        result,
                    )
                except Exception as e:
                    logger.warning(f"Conclave: editor упал ({e}), продолжаю без редактуры")

            if self.should_stop:
                self._progress(_pick("stopped"))
                break

            # --- Машинная проверка кодовой ветки (не «модель судит модель») ---
            machine = self._machine_check(result, executor_name)

            # --- Critic ---
            score, feedback = self._run_critic(task, result, machine["note"] if machine else "")
            # Битый синтаксис нельзя «принять по ощущению» — глушим оценку, чтобы
            # цикл пошёл на ещё одну итерацию с конкретной машинной ошибкой.
            if machine and machine["hard_fail"]:
                score = min(score, 4)
                feedback = f"{machine['note']}\n{feedback}".strip()
            last_feedback = feedback
            logger.info(f"Conclave: iter={iteration} critic_score={score}"
                        + (f" [{machine['note'][:60]}]" if machine else ""))

            if score > best_score:
                best_score  = score
                best_result = result

            # Принимаем если достаточно хорошо
            if score >= PASS_SCORE:
                self._progress(_pick("accept"))
                logger.info(f"Conclave: принято на итерации {iteration}, score={score}")
                break

            # Стагнация — оценка не растёт
            if score <= prev_score:
                stagnation += 1
                if stagnation >= 2:
                    self._progress(_pick("stagnation"))
                    logger.info(f"Conclave: стагнация {stagnation}, best_score={best_score}")
                    break
            else:
                stagnation = 0

            prev_score = score

            if iteration < MAX_ITER and not self.should_stop:
                self._progress(_pick("retry"))

        if not best_result:
            best_result = "[Конклав не смог получить результат]"

        dt = time.time() - t_start
        logger.info(f"Conclave.run_with_qa завершён: best_score={best_score}, итераций={iteration}, время={dt:.1f}s")
        return best_result

    def _machine_check(self, result: str, executor_name: str) -> dict | None:
        """Кодовую ветку проверяем машиной, а не только critic'ом.

        ast.parse (синтаксис) → hard_fail (битый код нельзя «принять по
        ощущению»). Прогон в firejail-песочнице — информативно для критика, НЕ
        hard_fail: код может требовать вход/контекст и падать вне его, это не
        всегда дефект. Возвращает {note, hard_fail} или None если это не код."""
        if executor_name != "coder":
            return None
        code = _extract_python(result)
        if not code:
            return None
        import ast
        try:
            ast.parse(code)
        except SyntaxError as e:
            return {"note": f"⚙ Машинная проверка: СИНТАКСИС НЕ ВАЛИДЕН (строка {e.lineno}): {e.msg}",
                    "hard_fail": True}
        note = "⚙ Машинная проверка: синтаксис валиден"
        try:
            from tools.shell_tools import run_python
            out = run_python(code, "conclave")   # возвращает dict, не JSON-строку
            if out.get("ok"):
                so = (out.get("stdout") or "").strip()
                note += "; прогон без ошибок" + (f", вывод: {so[:200]}" if so else " (без вывода)")
            else:
                err = (out.get("error") or out.get("stderr") or "").strip()
                if any(k in err.lower() for k in ("firejail", "sandbox", "изоляц", "песочниц")):
                    note += "; прогон пропущен (нет песочницы)"
                else:
                    note += f"; ПРОГОН УПАЛ: {err[:200]}"
        except Exception as e:
            note += f"; прогон не выполнен ({e})"
        return {"note": note, "hard_fail": False}

    def _run_critic(self, task: str, result: str, machine_note: str = "") -> tuple[int, str]:
        """
        Запускает critic и парсит оценку.
        machine_note — результат машинной проверки кода (синтаксис/прогон), если
        есть; критик обязан опираться на него, а не только на «ощущение».
        Возвращает (score: 0–10, feedback: str). При ошибке — нейтральный score=5.
        """
        try:
            config = _load_config("critic")
            prompt = (
                f"Задача:\n{task}\n\n"
                f"Результат:\n{result}\n\n"
                + (f"{machine_note}\n\n" if machine_note else "")
                + "Оцени результат по шкале 0–10. Если это код — оценивай РАБОТОСПОСОБНОСТЬ "
                  "(опирайся на машинную проверку выше: синтаксис/прогон), а не только "
                  "аккуратность.\n"
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
