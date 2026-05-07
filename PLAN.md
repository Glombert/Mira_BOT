# Mira_BOT — План разработки

> Версия: 3.5
> Последнее обновление: 2026-05-07
> Архитектура: см. ARCHITECTURE.md

---

## Что изменилось в v3.5

Telegram Bot и инструменты для Excel — запущено и протестировано в боевом режиме:

- **Telegram Bot (`telegram_bot.py`).** Полноценный бот: приём сообщений, классификация роутером, маршрутизация в Конклав или Альфу. Per-user сессии в `memory/sessions/tg_{id}.json`. Workspace изолирован на пользователя.
- **Owner detection.** `OWNER_TELEGRAM_ID` в `.env` — для Telegram. `/evolve`, `/reflect`, `/git`, `/release`, `/users`, `/approve`, `/block` — только для owner.
- **`/evolve` в Telegram — неинтерактивный.** Diff → inline-кнопки ✅/❌ вместо `input()`. Без блокировки event loop.
- **Inline-кнопки.** `/help`, heartbeat Конклава, подтверждение `/evolve` и `/release` — всё через `InlineKeyboardMarkup`.
- **Автоотправка файлов.** После каждого ответа Мира проверяет `output/` и отправляет новые файлы пользователю.
- **Загрузка документов.** `handle_document()` — файл сохраняется в `inbox/` пользователя, Мира подтверждает.
- **Excel-инструменты (`tools/excel_tools.py`).** `excel_read` (до 200 строк, поддержка sheet_name, заголовки авто), `excel_write` (overwrite с `.undo/` бэкапом). Агент `agents/excel_specialist.json` — рабочий.
- **systemd-сервис — **не локально**, а на VPS.** Деплой запланирован на Этап 7. Пока бот запускается вручную: `python telegram_bot.py`.

## Что изменилось в v3.4

Полный прогон тестирования — выявлены и закрыты баги, подтверждена работа системы:

- **Модель через точку.** `claude-sonnet-4-6` → `claude-sonnet-4.6` (OpenRouter не матчил дефис, запрос уходил на DeepSeek).
- **ChatCompletionMessage → dict.** В `Agent.run()` объект tool_calls теперь конвертируется в dict перед добавлением в messages. Иначе `trim_history()` и `_apply_prompt_caching()` падали.
- **`/evolve` через unified diff.** Раньше модель возвращала полный файл — при ~1500 строках это 40k токенов, которые обрезались при `max_tokens=4096`. Теперь модель возвращает только diff (~10 токенов на одну строку). Добавлен `_apply_unified_diff()`.
- **`smoke_test` с `PYTHONPATH`.** `cwd` не помогает — Python добавляет в `sys.path` директорию скрипта (`/tmp/`), а не cwd. Теперь передаём `PYTHONPATH=project_dir`.
- **`/git` и `/release` только для owner.** Раньше хватало `--profile dev`, теперь нужен `user_status == "owner"` + `profile.can_use()`.
- **`run_onboarding()` и `reflect()` на `providers.call()`.** Убраны все прямые `client.chat.completions.create()`. В `agent.py` не осталось ни одного прямого вызова API.
- **Prompt caching.** `_apply_prompt_caching()` в `providers.py`: для Anthropic-моделей через OpenRouter системное сообщение конвертируется в блочный формат с `cache_control: {"type": "ephemeral"}`.
- **Полный цикл /evolve подтверждён.** diff → принципы OK → backup → syntax → smoke-test → запись → /git → /release → main обновлён.

## Что изменилось в v3.3

После обсуждения провайдерной стратегии и проверки актуального рынка моделей:

- **OpenRouter — основной провайдер.** Один баланс пополнить проще, чем три. Накрутка ~5% компенсируется удобством.
- **Прямые API — резервные.** Anthropic и DeepSeek ключи остаются в `.env` на случай сбоев OpenRouter. Anthropic-ключ всё равно нужен для Claude Code, переиспользуем.
- **`model_chain` в каждом агенте.** Список из 2–3 моделей по убыванию приоритета. При сбое первой — переход к следующей.
- **Актуальные модели мая 2026.** Claude Opus/Sonnet/Haiku 4.7/4.6/4.5, DeepSeek V4 Pro/Flash, Gemini 3.1 Pro, Perplexity Sonar.
- **Распределение специализаций.** Альфа/Coder: Claude. Critic: Gemini (другая модель — свежий взгляд). Scout: Perplexity. Editor/Reviewer: DeepSeek (дёшево и качественно).
- **Perplexity-Scout** перенесён из бэклога в Этап 2 — теперь это конфиг агента в одну строку.
- **Деградация явная.** Когда Мира работает через резерв, она об этом знает и может упомянуть.

---

## Главный принцип: качественно и легко

Сервер — VPS на 1–2 ядра и 512 МБ–2 ГБ ОЗУ. Цель — **качественный помощник для нескольких пользователей**, не платформа для всего.

- Никаких тяжёлых БД. JSON → SQLite → Postgres (по нарастающей).
- Никаких очередей задач. Один процесс с in-memory очередью.
- Никаких микросервисов.
- Параллелизм — `concurrent.futures` в том же процессе.
- ChromaDB — только когда упрёмся.

Каждая фича проходит фильтр: **«нужно ли это маме?»**

---

## Текущее состояние

- [x] Базовый агент с историей диалога, tool calling, ротируемые логи
- [x] providers.py: model_chain, fallback-цепочка, prompt caching для Anthropic/OpenRouter
- [x] Этапы 0.1–0.8 (фундамент, безопасность, ветки, облако, доступ)
- [x] Этапы 1.1–1.6, 1.8 (Agent класс, file/shell/git/cloud/access tools, /undo, лимиты, инъекции)
- [x] /evolve через unified diff — работает на файлах любого размера
- [x] Полный цикл саморедактирования протестирован вживую (diff → принципы → smoke-test → /release → main)

---

## Архитектура моделей и провайдеров

### API-ключи в `.env`

```
# ОСНОВНОЙ
API_OPENROUTER_KEY=sk-or-v1-...
API_OPENROUTER_URL=https://openrouter.ai/api/v1

# РЕЗЕРВНЫЕ (на случай сбоя OpenRouter)
ANTHROPIC_API_KEY=...        # переиспользуем тот, что для Claude Code
DEEPSEEK_API_KEY=...         # уже есть
```

Три ключа покрывают всё. OpenRouter даёт доступ к 200+ моделям через один счёт. Прямые API остаются как страховка.

### Распределение ролей и моделей (актуально на май 2026)

| Роль | Основная (OpenRouter) | Резерв 1 (OpenRouter) | Резерв 2 (Direct) |
|---|---|---|---|
| **Альфа** (общение) | `anthropic/claude-sonnet-4.6` | `deepseek/deepseek-v4-flash` | Anthropic direct |
| **Coder** | `anthropic/claude-sonnet-4.6` | `anthropic/claude-opus-4.7` | Anthropic direct |
| **Critic** | `google/gemini-3.1-pro-preview` | `anthropic/claude-sonnet-4.6` | — |
| **Scout** | `perplexity/sonar` | `perplexity/sonar-pro` | — |
| **Editor** | `deepseek/deepseek-v4-flash` | `anthropic/claude-haiku-4.5` | DeepSeek direct |
| **Reviewer** | `deepseek/deepseek-v4-flash` | `anthropic/claude-sonnet-4.6` | DeepSeek direct |
| **Planner** | `anthropic/claude-sonnet-4.6` | `deepseek/deepseek-v4-pro` | Anthropic direct |
| **Onboarding** | `anthropic/claude-sonnet-4.6` | `deepseek/deepseek-v4-flash` | — |

**Логика выбора:**
- **Claude Sonnet 4.6** — основная рабочая лошадка. По бенчмаркам конкурирует с прошлым Opus, цена ниже. Идеален для Альфы, Coder'а, Planner'а.
- **Claude Opus 4.7** — для тяжёлой эволюции кода. Включается как резерв 1 для Coder'а — если Sonnet не справился, пробуем Opus.
- **Claude Haiku 4.5** — самый дешёвый Claude. Для Editor'а как резерв.
- **DeepSeek V4 Flash** — дешёвый, мощный, отличный для вспомогательных ролей (Editor, Reviewer).
- **Gemini 3.1 Pro для critic** — намеренно другая модель и провайдер, чтобы критик не повторял предубеждений Альфы. Это ключевой момент мульти-агентного дизайна.
- **Perplexity Sonar для scout** — единственный со встроенным поиском и цитатами.

### Формат `agents/{name}.json` с цепочкой моделей

```json
{
  "name": "Coder",
  "role": "executor",
  "system_prompt": "Ты пишешь код качественно...",
  "model_chain": [
    { "provider": "openrouter", "model": "anthropic/claude-sonnet-4.6", "temperature": 0.3 },
    { "provider": "openrouter", "model": "anthropic/claude-opus-4.7",   "temperature": 0.3 },
    { "provider": "anthropic",  "model": "claude-sonnet-4.6",            "temperature": 0.3 }
  ],
  "max_tokens": 4096,
  "allowed_tools": ["read_file", "write_file", "run_python"]
}
```

### Правила резервирования

1. **«Сбой» = что-то из списка:** сетевая ошибка, таймаут (30 сек), HTTP 429, HTTP 5xx, пустой ответ.
2. **Один retry на провайдере** → переход к следующему. Не долбим один и тот же.
3. **Каждое переключение** пишется в `memory/decisions.log`.
4. **Если переключений >5 за сутки** — уведомление владельцу: «провайдер X нестабилен».
5. **Деградация осознанная.** В системный промпт добавляется строка «ты работаешь через резерв, можешь упомянуть если уместно».
6. **Смена основной модели** — только владельцем через `/release`. Никаких автоподмен «потому что дешевле».

### Обновление списка моделей

Модели меняются часто. Список выше зафиксирован на дату документа. Раз в квартал (или когда Мира предложит сама — см. бэклог Model Scout) — пересматриваем актуальные имена и обновляем `agents/*.json`.

---

## Принятые архитектурные решения

### Самоизменение и пользователи

`agent.py` — единое ядро. `/evolve` только в профиле `dev`. Мира меняет конфиги в `agents/`, память в `memory/`. Новые агенты — это не изменение ядра.

### PRINCIPLES.md — конституция

`persona.json` — характер (изменяемый). `PRINCIPLES.md` — правила (нерушимые). При `/evolve` Мира перечитывает PRINCIPLES, прогоняет diff через проверку, потом показывает пользователю.

### Ветка mira-dev для эволюции

`main` — релизная, ручные мерджи. `mira-dev` — рабочая. `/release` мерджит в `main`. VPS пуллит только `main`.

### Резервирование: rclone + Google Drive

`memory/` и `versions/` синхронизируются через `rclone crypt`. Развёртывание на новой машине — три команды.

### Тестирование делает Конклав

Pytest — для критичных мест. Остальное — Конклав через цикл executor → editor → critic → reviewer.

### Защиты от циклов в Конклаве

Пять механизмов в `Conclave.run_with_qa()`:
1. **Жёсткий лимит итераций с сохранением.** Максимум 3 круга, после третьего — лучший результат с припиской.
2. **Critic ставит оценку 0–10.** ≥7 — принимаем. Снимает перфекционизм.
3. **Прогресс-метрика.** Не растёт 2 итерации подряд — стоп.
4. **Heartbeat пользователю.** На каждой итерации Альфа пишет статус.
5. **Killswitch.** `/stop` отдаёт «что есть».

### Трёхуровневая система доступа

Owner / regular / guest / blocked — поле `status` в профиле.

| Статус | Может |
|---|---|
| `owner` | Всё, включая `/evolve`, `/release`, одобрение |
| `regular` | Полный доступ к своему workspace и Конклаву |
| `guest` | Только разговор, 10 сообщений, ждёт одобрения |
| `blocked` | Ничего |

Гостевой флоу: знакомство → уведомление владельцу → лимит 10 сообщений → ожидание → авто-удаление через 3 дня. При одобрении история сохраняется. Гостевой профиль (`profiles/guest.json`) — пустой `allowed_tools`.

### Структура workspace пользователя

```
workspace/{user_id}/
    ├── inbox/      ← пользователь кидает файлы
    ├── output/     ← Мира кладёт результаты
    ├── temp/       ← временное, автоочистка через 7 дней
    └── .undo/      ← бэкапы перед изменениями
```

---

## Целевая структура проекта

```
mira_bot/
├── agent.py                    # Тонкий запуск Альфы
├── conclave.py                 # Оркестратор Конклава
├── router.py                   # Классификатор задач
├── providers.py                # ← НОВОЕ. Логика model_chain и fallback
│
├── PRINCIPLES.md / persona.json
├── ARCHITECTURE.md / PLAN.md / README.md / requirements.txt
├── .env / .profile / .gitignore
│
├── agents/
│   ├── _template.json
│   ├── alpha.json
│   ├── planner.json / coder.json / excel_specialist.json
│   ├── editor.json / critic.json / reviewer.json
│   └── scout.json              # ← НОВОЕ. Perplexity для поиска
│
├── profiles/
│   ├── default.json (regular) / dev.json (owner) / accountant.json / guest.json
│
├── tools/
│   ├── file_tools.py ✓ / shell_tools.py ✓
│   ├── excel_tools.py / web_tools.py
│   ├── git_tools.py / cloud_tools.py
│   └── access_tools.py
│
├── workspace/{user_id}/        # Только regular и owner
├── memory/                     # Профили, сессии, журнал, providers_status
├── versions/                   # Бэкапы agent.py
└── tests/                      # Минимум pytest
```

---

## Этапы разработки

---

### ЭТАП 0 — Фундамент ✓

#### 0.1–0.5 ✓

#### 0.6 ✓ — Безопасность саморедактирования

**0.6.1 PRINCIPLES.md** ✓
- [x] `PRINCIPLES.md` создан (5 разделов: саморедактирование, данные, доступ, инъекции, саморасширение).
- [x] `load_principles()` в `agent.py`.
- [x] При `/evolve` — принципы вшиваются в системный промпт генерации.
- [x] Отдельный API-вызов проверяет diff на соответствие принципам.
- [x] При нарушениях — предупреждение, решение за пользователем.

**0.6.2 Ветка mira-dev** ✓
- [x] `mira-dev` создана локально и на GitHub.
- [x] `ensure_dev_branch()` в `tools/git_tools.py`.
- [x] `/evolve` переключается на `mira-dev` до генерации.
- [x] `/release` — merge --no-ff mira-dev → main с подтверждением.
- [ ] GitHub branch protection для `main` — настраивается вручную в настройках репозитория.

**0.6.3 MAX_TOOL_ROUNDS** ✓
- [x] Вынесен в профиль (`max_tool_rounds: 30`). `Agent.run()` берёт из профиля.

#### 0.7 ✓ — Резервирование (инфраструктура)

- [ ] Установить `rclone` и настроить `rclone crypt` — на усмотрение пользователя.
- [x] `RCLONE_REMOTE` в `.env` (задокументировано, код проверяет).
- [x] `tools/cloud_tools.py`: `cloud_sync()`, `cloud_restore()`.
- [x] Команды `/cloud sync`, `/cloud restore`.
- [x] Авто-синхронизация при штатном выходе (если `RCLONE_REMOTE` задан).
- [ ] README с тремя командами для развёртывания — отложено до Этапа 7.

#### 0.8 ✓ — Доступ и многопользовательность

**0.8.1–0.8.4** ✓
- [x] Поле `status`: owner / regular / guest / blocked в `memory/{user_id}.json`.
- [x] `OWNER_CLI_USER` в `.env` — для CLI. `OWNER_TELEGRAM_ID` — в Этапе 4.
- [x] `profiles/guest.json` — пустой `allowed_tools`, `max_history: 10`.
- [x] Счётчик сообщений гостя, лимит 10, напоминание при ≤3 оставшихся.
- [x] Авто-удаление гостей через 3 дня (`cleanup_expired_guests()`).
- [x] `tools/access_tools.py`: `list_users()`, `approve()`, `reject()`, `block()`, `unblock()`, `notify_owner()`.
- [x] Команды `/users`, `/approve`, `/reject`, `/block`, `/unblock` (только owner).
- [x] `notify_owner()` пишет в лог и `decisions.log`; Telegram — в Этапе 4.

**0.8.5 Маскировка секретов** — частично
- [ ] Маскировка содержимого файлов при логировании tool_args — не реализована.
- [ ] Проверка прав `.env` при старте — не реализована.

---

### ЭТАП 1 — Класс Agent + защита от себя ✓

#### 1.1 ✓ — Рефакторинг + провайдеры с резервированием
- [x] Класс `Agent`: `run()`, `can_use()`, `use_tool()`, `from_config_file()`.
- [x] `providers.py`: `PROVIDERS`, `call(model_chain, messages, **kwargs)`, логирование переключений в `decisions.log`.
- [x] `_apply_prompt_caching()`: для Anthropic/OpenRouter добавляет `cache_control: {"type": "ephemeral"}` к системному сообщению.
- [x] Конфиг агента из `agents/{name}.json` с `model_chain`.
- [x] Двойная проверка прав: агент + профиль пользователя (`profile.can_use(tool)`).
- [x] `tools/git_tools.py`: `sync_with_git()`, `ensure_dev_branch()`, `release_to_main()`.
- [x] `/git` и `/release` только для `user_status == "owner"`.

#### 1.2 ✓ — Function calling

#### 1.3 ✓ — file_tools (5 MB лимит, 100 MB workspace)

#### 1.4 ✓ — shell_tools

#### 1.5 ✓ — `/undo`
- [x] `_save_undo()` перед `write_file` с `overwrite=True` → `.undo/{timestamp}_{filename}`.
- [x] `undo_last()` восстанавливает в `output/undo_*`.
- [x] Хранит последние 10 версий.

#### 1.6 ✓ — Лимиты на файлы и память
- [x] Лимит файла: 5 MB. Лимит workspace: 100 MB.
- [ ] Сжатие истории при >200 сообщениях — отложено в Этап 5.

#### 1.7 ✓ — Prompt caching
- [x] `_apply_prompt_caching()` в `providers.py` для `openrouter + anthropic/*`.
- [ ] Кеширование для Google/Gemini — при добавлении Этапа 2.

#### 1.8 ✓ — Защита от промпт-инъекций
- [x] `execute_tool()` оборачивает результат `read_file` в маркеры `--- BEGIN/END USER FILE ---`.
- [x] В `PRINCIPLES.md` — правило о маркерах.

#### Дополнительно (найдено в ходе тестирования) ✓
- [x] `/evolve` — unified diff вместо полного файла. `_apply_unified_diff()` без внешних зависимостей.
- [x] `smoke_test()` — `PYTHONPATH=project_dir` чтобы `tools/` находился из `/tmp/`.
- [x] `Agent.run()` — tool_calls сообщение конвертируется в dict (иначе `trim_history` и `_apply_prompt_caching` падали).
- [x] Имя модели: `claude-sonnet-4-6` → `claude-sonnet-4.6` (OpenRouter требует точку).

---

### ЭТАП 2 — Конклав (мультиагентность + ОТК + защиты) ✓

#### 2.1 ✓ — Оркестратор и роутер
- [x] `router.py` — `classify(message, model_chain) -> "chat"|"files"|"code"|"complex"`.
      Один вызов, temperature=0, max_tokens=5. Fallback → "chat".
- [x] `conclave.py` — класс `Conclave`. Нет circular import: работает напрямую через `providers.call()`.
- [x] `Conclave.run(name, task)` — одиночный запуск специалиста.
- [x] `Conclave.run_with_qa(task, executor)` — цикл executor→editor→critic, все 4 защиты.

#### 2.2 ✓ — Конфиги специалистов
- [x] `agents/planner.json` — Claude Sonnet 4.6 → deepseek-chat.
- [x] `agents/coder.json` — Claude Opus 4.7 → Claude Sonnet 4.6.
- [x] `agents/excel_specialist.json` — заглушка для Этапа 3.

#### 2.3 ✓ — ОТК
- [x] `agents/editor.json` — DeepSeek Chat → Claude Haiku 4.5.
- [x] `agents/critic.json` — **Gemini 2.0 Flash** (намеренно другой провайдер!) → Claude Sonnet 4.6.
- [x] `agents/reviewer.json` — DeepSeek Chat → Claude Sonnet 4.6.
- [x] `agents/scout.json` — Perplexity Sonar → Sonar Pro.
- [x] Защиты: max 3 итерации, оценка ≥7, стагнация 2 итерации → стоп, heartbeat.

#### 2.4 ✓ — Killswitch
- [x] `conclave.should_stop` — флаг прерывания.
- [x] Команда `/stop` в agent.py — выставляет флаг, Конклав останавливается между итерациями.

#### 2.5 — notify vs ask
- [ ] Два режима Альфы — в Telegram (Этап 4).

#### 2.6 — Параллелизм
- [ ] `Conclave.run_parallel(tasks)` через `concurrent.futures` — отложено до Этапа 4.

#### 2.7 — Интеграция с /evolve
- [ ] `/evolve` через `run_with_qa` — отложено до Этапа 6 (тесты должны быть готовы).

#### 2.8 ✓ — Scout (Perplexity)
- [x] `agents/scout.json` создан. Доступен через `Conclave.run("scout", task)`.

#### 2.9 — Саморасширение
- [ ] `spawn_agent` — Этап 4+.

---

### ЭТАП 3 — Excel и табличная обработка данных ✓

- [x] `tools/excel_tools.py` (openpyxl): `excel_read`, `excel_write`.
- [x] Полный сценарий — от текстового описания до заполненной таблицы.
- [ ] Профиль `profiles/accountant.json` — отложено, нет готового сценария.
- [x] `agents/excel_specialist.json` — рабочий агент.

---

### ЭТАП 4 — Telegram Bot ✓

- [x] Telegram Bot (`python-telegram-bot 22+`): сообщения, документы, кнопки.
- [x] `_user_id(tg_id)` → `"tg_{tg_id}"` — per-user сессии и workspace.
- [x] **Активация трёхуровневой системы доступа** — `OWNER_TELEGRAM_ID`, owner-команды, guest-лимиты.
- [x] `/evolve` в Telegram — diff + inline-кнопки ✅/❌.
- [x] `/stop` через inline-кнопку в heartbeat-сообщении.
- [x] Автоотправка файлов из `output/` после каждого ответа.
- [ ] Web UI (FastAPI) — не нужен, пока Telegram покрывает.
- [ ] **Деплой (systemd + nginx)** — на VPS, Этап 7. Пока: `python telegram_bot.py` вручную.

---

### ЭТАП 5 — Долгая память

- [ ] `memory/decisions.log` — журнал важных решений.
- [ ] Мира сама обновляет профиль пользователя при появлении новой инфы.
- [ ] Ротация sessions: последние 30 дней, старые сжимаются в summary.
- [ ] Шаблоны задач (`memory/templates/{user_id}/`) — повторяющиеся задачи в один шаблон.
- [ ] ChromaDB опционально, если упрёмся в семантический поиск.

---

### ЭТАП 6 — Тесты

- [ ] `tests/test_file_tools.py` — sandbox, overwrite, размер.
- [ ] `tests/test_shell_tools.py` — таймаут, обрезание, очистка tmp.
- [ ] `tests/test_git_branch.py` — переключение, /release.
- [ ] `tests/test_conclave_loops.py` — цикл с критиком завершается на 3 итерации.
- [ ] `tests/test_access.py` — статусы, гостевой лимит, авто-удаление.
- [ ] `tests/test_providers.py` — fallback цепочка работает при сбое.

---

### ЭТАП 7 — Деплой и мониторинг

- [ ] Алерт в Telegram при падении агента.
- [ ] Бэкап `memory/` раз в сутки через rclone (cron).
- [ ] Nginx + HTTPS.
- [ ] Health-check эндпойнт.
- [ ] Структурированное логирование (JSON-lines).
- [ ] **Изоляция `run_python` через Docker или firejail** — обязательно перед тем, как давать regular-пользователям.

---

## Бэклог

### Полезное — добавим, когда упрёмся
- **Scheduled Tasks** — инфраструктура запланированных задач (Мира помнит, что и когда делать).
- **Model Scout** — раз в месяц анализ новых моделей через OpenRouter `/models` API, отчёт владельцу. Зависит от Scheduled Tasks.
- **Метрики использования** (токены/задачи/время на пользователя).
- **Версионирование персоны и принципов** — откат через симлинк.
- **A/B-сравнение моделей** на одной задаче.
- **Background consciousness** — Мира думает между задачами. Только после Telegram.
- **Экспорт/импорт профиля** — для переезда.
- **Голосовой ввод/вывод** (Whisper + TTS).
- **Самонастраивающиеся лимиты антиспама** — Мира анализирует историю и подкручивает пороги.

### Заманчиво, но не наш масштаб — возможно никогда
- Защита от массовой регистрации (актуально только при выходе на рынок).
- Мульти-сервер с балансировкой.
- Своя векторная БД на embeddings.
- Тонкая настройка моделей (fine-tuning).
- Плагины от третьих сторон.
- Маркетплейс агентов.
- Своё мобильное приложение.

---

## Что НЕ делаем (зафиксированные решения)

| Идея | Почему нет |
|---|---|
| Бюджет в коде | Опыт Ouroboros: при срабатывании агент сухой, перенастройка через код и рестарт — раздражает. |
| Background consciousness в CLI | Бесполезно, пока пользователь сам в терминале. |
| Google Colab как рантайм | Костыль для бесплатного compute. |
| Свой sandbox-движок | Подпроцесс с таймаутом + Docker (Этап 7) достаточно. |
| Своя векторная БД с нуля | ChromaDB решает задачу. |
| Своя авторизация | Telegram даёт `user_id` бесплатно. |
| Очереди задач (Celery, Redis) | Один процесс с `concurrent.futures` покрывает наш масштаб. |
| Микросервисы | Один процесс, понятная структура. |
| Postgres / MySQL | JSON → SQLite → Postgres. Мы в JSON. |
| Своё мобильное приложение | Telegram покрывает. |
| Whitelist по IP / hardcoded списки | Заменено на трёхуровневую систему доступа. |
| Все API напрямую | Сложно пополнять. OpenRouter основной, прямые — резерв. |

---

## Порядок работы

1. Берём следующий незакрытый пункт.
2. Я объясняю, что и зачем.
3. Пишу код, ты запускаешь.
4. Говоришь, что работает, что нет — итерируем.
5. Ставим галочку, идём дальше.

При каждом новом сеансе — закидываешь актуальный `agent.py` и этот `PLAN.md`.

---

## Текущий статус

```
[x] ЭТАП 0   — Фундамент (0.1–0.8 полностью)
[x] ЭТАП 1   — Agent класс + инструменты + защиты (1.1–1.8 полностью)
[x] ЭТАП 2   — Конклав: router.py, conclave.py, 7 конфигов агентов, /stop
              Отложено: параллелизм, /evolve через QA, spawn_agent
[x] ЭТАП 3   — Excel: excel_read, excel_write, excel_specialist
[x] ЭТАП 4   — Telegram Bot: сессии, owner-команды, inline-кнопки, файлы
              Отложено: Web UI (не нужен), деплой → VPS (Этап 7)
[ ] ЭТАП 5   — Долгая память + ротация + шаблоны     ← СЛЕДУЮЩИЙ
[ ] ЭТАП 6   — Тесты
[ ] ЭТАП 7   — VPS: деплой, systemd, nginx, мониторинг, изоляция run_python
```
