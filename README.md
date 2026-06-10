<div align="center">

# 🌟 Mira

### Личный AI-ассистент, который живёт сразу в Telegram, в браузере, на десктопе и в телефоне

<sub>🇷🇺 Русский · [🇬🇧 English](README.en.md)</sub>

[![Version](https://img.shields.io/badge/version-2.4-brightgreen?style=for-the-badge)](https://github.com/Glombert/Mira_BOT/releases)
[![Mobile](https://img.shields.io/badge/Mobile-Android_APK-FF8C42?style=for-the-badge&logo=android&logoColor=white)](https://github.com/Glombert/Mira_Mobile/releases/latest)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-22C55E?style=for-the-badge)](LICENSE)

<sub>**Модели:** Claude · DeepSeek · Gemini · OpenRouter &nbsp;·&nbsp; **Интеграции:** Telegram · Google Drive · Calendar · Sheets</sub>

<br/>

> *«Что нужно сделать завтра в 8 утра?» — пишешь в любом интерфейсе, в 8 утра Мира сама присылает то, что нужно.*

</div>

---

## Что это такое (по-человечески)

Mira — это **твой собственный AI-ассистент**, к которому можно обратиться через любое удобное окно: Telegram-бот, приложение на телефоне, веб-сайт или десктоп. **Один и тот же диалог, один и тот же контекст** — всё синхронизируется.

В отличие от облачных чат-ботов, Мира:

- 🧠 **Помнит тебя** между сессиями — имя, проекты, привычки, разговоры неделями назад
- 🔧 **Делает дела сама** — не просто отвечает, а лезет в твои файлы, открывает календарь, читает Google Sheets, качает с Drive
- ⏰ **Работает в фоне** — «завтра в 8:00 подготовь отчёт по продажам» → в 8:00 приходит push с готовым результатом
- 🤖 **Проверяет и улучшает себя** — раз в две недели сама ревьюит свой код, ищет уязвимости, разбирает логи на ошибки, следит за выходом новых моделей
- 🔄 **Не падает на одном провайдере** — Claude недоступен → DeepSeek → Gemini, всё прозрачно
- 🛡 **Твоя** — крутится на твоём VPS, никаких облачных подписок, ключи API только у тебя

## Примеры из жизни

```
ты:    «Привет, что сегодня было важного?»
Мира:  Смотрит твою историю, calendar, последние сообщения → выдаёт сводку.

ты:    [прикрепляешь PDF] «Что тут?»
Мира:  Читает, выдаёт резюме, при желании создаёт Excel с ключевыми данными.

ты:    «/task в пятницу 15:00 проверь статус задач у команды и подготовь отчёт»
Мира:  В пятницу 15:00 — push на телефон с готовым отчётом.

ты:    «Поищи последние новости по Python 3.13»
Мира:  Веб-поиск, выдержки, ссылки.

ты:    «Создай Google Sheet с расходами за май»
Мира:  Sheet создан, файл расшарен на твой email.
```

## Архитектура (для тех, кому интересно)

<div align="center">

```
                  ┌─────────────────────────────────────┐
                  │      ТЫ — один голос, любое окно     │
                  └──────────────┬──────────────────────┘
       ┌──────────┬──────────────┼──────────────┐
       ▼          ▼              ▼              ▼
   📱 Mobile   💻 Web        🖥 Desktop      💬 Telegram
   (RN)       (Next.js)     (Tauri v2)      (бот)
       │          │              │              │
       └──────────┴──────┬───────┴──────────────┘
                         │ WebSocket / HTTP
                         ▼
              ┌──────────────────────────┐
              │     МИРА (Альфа)         │
              │  • диалог, контекст      │
              │  • память пользователя   │
              │  • отвечает САМА +       │
              │    вызывает инструменты  │
              └────────────┬─────────────┘
                           │ фоном (ритуалы, scheduled tasks)
                           ▼
              ┌────────────────────────────┐
              │   АВТОНОМИЯ + КОНКЛАВ       │
              ├────────────────────────────┤
              │ Ритуалы (cron + LLM)       │
              │ Scheduled tasks            │
              │ Конклав-пайплайн:          │
              │  Coder → Editor → Critic   │
              └────────────────────────────┘
```

</div>

**Один голос — Мира.** В чате она **отвечает сама** (`alpha.run` с инструментами: поиск, код, календарь, картинки, генерация изображений). Конклав-пайплайн специалистов (Coder → Editor → Critic) работает в **фоновых задачах и ритуалах**, а не прогоняется на каждое сообщение чата.

## Что под капотом

| Слой | Технологии |
|---|---|
| **LLM-стек** | Claude Sonnet 4.6 / Opus 4.8 (Anthropic) · DeepSeek V4 · Gemini · OpenRouter (failover chain) |
| **Бэкенд** | Python 3.12 · FastAPI · WebSocket · python-telegram-bot · SQLite (WAL) · Fernet-шифрование памяти |
| **Контракт** | `web/ws_protocol.py` (pydantic) — единый источник истины WS/REST, парити-тест с TypeScript ловит дрейф |
| **Память** | Структурированное резюме · профили · ChromaDB (семантический поиск) |
| **Клиенты** | React Native (мобайл) · Next.js (веб) · Tauri v2 (десктоп) — монорепо с общими дизайн-токенами |
| **Push** | Firebase Cloud Messaging (FCM) |
| **Интеграции** | Google Drive · Calendar · Sheets · rclone · DuckDuckGo Search · Claude Vision |
| **Безопасность** | firejail-изоляция Python (fail-closed) · workspace per user · path traversal protection · HMAC-сессии |
| **Наблюдаемость** | Sentry-совместимый сбор ошибок (`SENTRY_DSN`) + redaction секретов в логах |
| **Самоэволюция** | `/evolve` — Мира правит свой код через многослойную валидацию (whitelist → syntax → smoke test → atomic rollback) |

## Структура монорепо

После слияния клиентов и бэкенда — один репозиторий:

```
mira_agent/
├── agent.py                                         ← класс Agent + персона (CLI-вход, мишень /evolve)
├── telegram_bot.py                                  ← entrypoint Telegram-бота (main + регистрация)
├── core/                                            ← ядро
│   ├── providers.py                                 ← LLM-провайдеры, failover, кэширование
│   ├── conclave.py, router.py                       ← Конклав и роутинг задач
│   ├── agent_tools.py                               ← реестр инструментов + execute_tool
│   └── memory_manager.py, memory_crypto.py          ← суммаризация и шифрование памяти
├── bot/                                             ← Telegram-слой
│   ├── chat.py, callbacks.py, files.py              ← сообщения, кнопки, документы
│   ├── commands_user.py / _owner.py / _tasks.py     ← команды по аудиториям
│   └── background.py, helpers.py, menu.py, config.py ← циклы ритуалов, хелперы
├── web/                                             ← FastAPI + WebSocket
│   ├── app.py                                       ← HTTP-роуты + WS-цикл
│   ├── ws_commands.py, sessions.py, alpha.py        ← WS-команды, сессии, запуск агента
│   ├── ritual_runner.py, panels.py                  ← фоновые ритуалы, данные экранов
│   ├── ws_protocol.py                               ← pydantic-контракт (источник истины)
│   ├── routes/                                      ← вынесенные роутеры (mobile, files, owner_inbox)
│   └── deps.py, security.py                         ← сессии, безопасность
├── agents/*.json                                    ← конфиги агентов (один класс, разные модели)
│   └── rituals/*.json                               ← фоновые задачи (cron + on_startup)
├── tools/                                           ← инструменты (Google, файлы, память, логи, …)
├── clients/                                         ← npm-воркспейсы веб/десктоп
│   ├── apps/web/                                    ← Next.js
│   ├── apps/desktop/                                ← Tauri v2
│   └── packages/shared/                             ← общие типы + дизайн-токены (TS)
├── mobile/                                          ← React Native (APK через CI → Mira_Mobile)
├── memory/                                          ← оперативные данные (mira.db, chroma, overlay)
└── scripts/                                         ← деплой, бэкап, релиз, smoke
```

`clients/packages/shared/src/tokens.ts` — единый источник дизайн-токенов (палитра, шрифты, радиусы): и веб (Tailwind), и мобайл (theme) берут значения отсюда — цвета не расходятся.

---

## Версии

### v2.4 — живое общение + самоулучшение

| Категория | Что |
|---|---|
| 🗣 **Голос Миры** | Убран router-гейт: каждое сообщение идёт к Мире с полным **ядром** (характер `persona.json` + регламент `RULES.md`/`behavior.md` + профиль), она отвечает сама и сама зовёт инструменты. Регламент: blacklist канцелярита/AI-клише, активный залог, рваный ритм, честность. |
| ✂️ **Живой ритм** | Длинный ответ дробится на 2–3 сообщения (реакция / основа / эпилог) с микро-задержкой; код-блоки и таблицы не режутся. |
| 💭 **Облако мысли** | Перед каждым `tool_call` — человекообразная подпись действия (`web_search` → «ищет в интернете…»). |
| 🤖 **Ритуалы самоулучшения** | Раз в 2 недели: `self_review` (рефакторинг + безопасность + идеи, на Opus), `log_audit` (повторяющиеся ошибки из логов), `agent_versions` (выход новых моделей), `weekly_summary` (статистика/стоимость). Ежедневно — `server_health` (живость + диск). |
| 🛠 **Тех-канал владельца** | Отдельный канал в приложении: ритуалы, ошибки, заявки. Двусторонний tech-режим (Мира в роли разработчика, сырые логи/стеки). `owner_inbox` (retention 30 дней) + WS-push + Telegram-fallback. |
| ✉️ **Сообщения между пользователями** | `find_user` / `send_to_user` с двухфактором (превью → подтверждение → доставка TG+FCM), блокировка отправителей. |
| ⚡ **Cache-split + persona overlay** | Маркер `<<MIRA_DYNAMIC>>` кэширует статичное ядро (Anthropic prompt caching). Soft-поля характера пишутся в `memory/persona_overlay.json` (git-untracked) — `git pull` на проде не конфликтует. |

### Раньше

- **v2.3** — security-аудит (OWASP ASVS/API/LLM Top-10), in-app обновление мобайла (PAT-прокси APK), Aurora-веб (1:1 с мобайлом), карточки памяти, экран «Профиль» + анкета.
- **v2.2** — per-user timezone, vision из приложений, smoke-suite, auto-release, logrotate.
- **v2.0–2.1** — мобайл/веб/десктоп-клиенты, one-tap Telegram-логин, drawer-меню, FCM push, ритуалы и scheduled tasks.

[**→ Полная история релизов**](https://github.com/Glombert/Mira_BOT/releases)

---

## Инструменты (39)

<details>
<summary>Развернуть полный список</summary>

| Категория | Инструменты |
|---|---|
| Файлы | `list_files`, `read_file`, `write_file`, `excel_read`, `excel_write`, `attach_file`, `save_template`, `list_templates` |
| Само-рефлексия | `list_self`, `read_self`, `recall`, `git_log`, `read_logs`, `metrics_read`, `write_persona`, `write_agent_config` |
| Веб + код | `web_search`, `run_python` (firejail-изоляция), `generate_image`, `openrouter_list_models`, `whats_new` |
| Google Drive | `gdrive_list`, `gdrive_read`, `gdrive_write` |
| Google Calendar | `gcal_list`, `gcal_create`, `gcal_quick_add` |
| Google Sheets | `gsheet_read`, `gsheet_write`, `gsheet_create` |
| Напоминания | `schedule_reminder`, `list_reminders`, `cancel_reminder` |
| Сообщения | `find_user`, `send_to_user`, `confirm_send_to_user`, `cancel_send_to_user`, `block_sender`, `unblock_sender` |

</details>

---

## Быстрый старт

### Локальная разработка (бэкенд)

```bash
git clone https://github.com/Glombert/Mira_BOT.git mira_agent
cd mira_agent
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Настрой `.env`:

```env
API_OPENROUTER_KEY=sk-or-v1-...
API_OPENROUTER_URL=https://openrouter.ai/api/v1
API_DEEPSEEK_KEY=sk-...
API_DEEPSEEK_URL=https://api.deepseek.com/v1
API_ANTHROPIC_KEY=sk-ant-...

TELEGRAM_BOT_TOKEN=...
OWNER_TELEGRAM_ID=123456789

# Опционально:
MEMORY_ENCRYPTION_KEY=...            # Fernet-ключ — шифрование памяти
SENTRY_DSN=...                       # сбор ошибок (без него выключено)
MIRA_MAX_CONCURRENT_LLM=6            # потолок одновременных LLM-вызовов на процесс
```

Запуск:

```bash
# Локально без firejail run_python заблокирован (fail-closed). Для разработки:
export MIRA_ALLOW_UNSANDBOXED=1
python telegram_bot.py                          # Telegram-бот
uvicorn web.app:app --host 127.0.0.1 --port 8000  # веб (FastAPI)
```

### Клиенты (веб / десктоп / мобайл)

```bash
cd clients && npm install            # воркспейсы web + desktop + packages/shared
npm --workspace apps/web run dev     # Next.js
# Desktop (Tauri): npm --workspace apps/desktop run tauri dev

cd ../mobile && npm install          # React Native (APK собирается только в CI)
```

> ⚠️ Тяжёлые нативные сборки (gradle / `react-native run-android`) — **только через CI**, не локально.

### Тесты

```bash
venv/bin/pytest -q                                  # бэкенд (407 тестов)
cd clients/apps/web && npx vitest run               # веб (vitest + RTL)
cd mobile && npx jest                               # мобайл (jest)
```

---

## Развёртывание на VPS

**1. Код + зависимости:**
```bash
git clone https://github.com/Glombert/Mira_BOT.git mira_agent
cd mira_agent && python3 -m venv venv && venv/bin/pip install -r requirements.txt
```

**2. Настрой `.env`** (как локально). **3. Восстанови память** (если переезд): `rclone copy gdrive:Mira/memory ./memory`.

**4. systemd-сервисы** `mira-bot` (Telegram) и `mira-web` (FastAPI). Шаблоны — в `scripts/mira-bot.service` / `scripts/mira-web.service`, включая лимиты памяти (важно, если на VPS живёт ещё и VPN):

```ini
# /etc/systemd/system/mira-web.service
[Service]
WorkingDirectory=/root/mira_agent
ExecStart=/root/mira_agent/venv/bin/uvicorn web.app:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5s
MemoryHigh=350M
MemoryMax=450M
TasksMax=256
```

```bash
systemctl daemon-reload && systemctl enable --now mira-bot mira-web
```

**5. Автодеплой (GitHub Actions):** секреты `SSH_PRIVATE_KEY`, `VPS_HOST`, `VPS_USER`; `.github/workflows/deploy.yml` обновляет сервер при пуше.

**6. Nginx + SSL (DuckDNS + acme.sh):** шаблон в `scripts/nginx.conf.example`, DNS-01 через duckdns.

**7. Бэкап памяти** (`/root/mira_backup.sh`, cron 3:00 UTC) — делает **консистентный снапшот SQLite** (online-backup API), синкает на Drive с `--backup-dir` (версионирование: изменённый/удалённый файл уезжает в датированный архив → point-in-time recovery), и шифрует `.env` GPG'ом офсайт:

```bash
# Парольную фразу сохрани в менеджере паролей — без неё restore невозможен
echo 'ТВОЯ_ФРАЗА' > /root/.mira_backup_pass && chmod 600 /root/.mira_backup_pass
```

---

## Disaster Recovery

**Что хранить вне сервера:** парольную фразу `backup_env.sh` (в менеджере паролей) + доступ к Google Drive (там зашифрованная память, `.env` и бэкапы кода).

```bash
# 1. зависимости + rclone remote 'gdrive:'
apt install -y python3.12 python3.12-venv rclone gpg firejail && rclone config
# 2. код
git clone https://github.com/Glombert/Mira_BOT.git /root/mira_agent && cd /root/mira_agent
python3 -m venv venv && venv/bin/pip install -r requirements.txt
# 3. зашифрованный .env
BACKUP_PASSPHRASE='ТВОЯ_ФРАЗА' ./scripts/restore_env.sh
# 4. память (mira.db.backup — консистентный снапшот) + история эволюции
rclone copy gdrive:Mira/memory ./memory && rclone copy gdrive:Mira/versions ./versions
# 5. сервисы
systemctl daemon-reload && systemctl enable --now mira-bot mira-web
```

После этого Мира знает всех пользователей, помнит разговоры, хранит свои рефлексии и видит историю эволюции.

---

## Архитектура (детально)

### Мира + Конклав

Один голос — Мира (агент `alpha`). Каждое сообщение **в чате** идёт к ней с полным ядром и профилем собеседника; она отвечает **сама**, вызывая инструменты (поиск, код, календарь, картинки). Роутера-врат, уводившего запрос «мимо» личности, нет.

```
чат → Мира (alpha) с полным ядром → отвечает сама, вызывая инструменты

фон (ритуалы, scheduled tasks) → Конклав-пайплайн:
        Кодер → Редактор → Критик  (цикл качества, оценка critic ≥7/10)
```

**Важно про Конклав:** пайплайн специалистов (Coder → Editor → Critic) сейчас работает **в фоновых задачах и ритуалах**, а не в каждом сообщении чата. Эскалация из чата к специалисту отдельным инструментом — в планах (пока Мира отвечает сама).

### Один класс — разные конфиги

```
agents/
  alpha.json              ← Мира, голос системы (Sonnet 4.6 → DeepSeek)
  coder.json              ← код (Opus 4.8 → Sonnet 4.6 → Anthropic direct)
  planner / editor / critic / reviewer / scout / excel_specialist / artist
  _template.json          ← базовый шаблон
  rituals/                ← фоновые задачи (см. ниже)
```

### Резервирование провайдеров

```json
{ "model_chain": [
    { "provider": "openrouter", "model": "anthropic/claude-sonnet-4.6" },
    { "provider": "openrouter", "model": "deepseek/deepseek-chat" },
    { "provider": "anthropic",  "model": "claude-sonnet-4.6" } ] }
```

При сбое первого — переход ко второму. Каждое переключение пишется в `memory/decisions.log` и уведомляет владельца. Стоимость каждого вызова — в `memory/metrics/` (видна через `metrics_read`).

### Ритуалы (автономия)

`agents/rituals/*.json` — cron + промпт + агент + порог уведомления:

| Ритуал | Когда | Агент | Что делает |
|---|---|---|---|
| `server_health` | ежедневно 00:00 | alpha | размер БД, диск, heartbeat |
| `self_review` | 1 и 15 числа | coder/Opus | рефакторинг + безопасность + идеи |
| `log_audit` | 1 и 15 числа | alpha | повторяющиеся ошибки из логов (`read_logs`) |
| `agent_versions` | 1 и 15 числа | alpha | вышли ли модели новее текущей |
| `weekly_summary` | 1 и 15 числа | alpha | статистика: юзеры, эволюции, стоимость LLM |

Доставка: `owner_inbox` + WS-push + Telegram-fallback (если IMPORTANCE ≥ порога). Защита от дублей — in-memory флаг «уже бежит».

### Память и логи

```
memory/
├── mira.db              ← SQLite WAL: профили, сессии, напоминания, рефлексии, owner_inbox
├── mira.db.backup       ← консистентный снапшот (для бэкапа)
├── chroma/              ← ChromaDB (семантический поиск)
├── persona_overlay.json ← soft-поля характера (git-untracked)
└── decisions.log        ← переключения провайдеров

logs/                    ← TimedRotatingFileHandler, retention 14 дней
└── telegram_bot.log, web.log (+ ротированные .YYYY-MM-DD)
```

Пользовательские данные в `mira.db` прозрачно шифруются Fernet (если задан `MEMORY_ENCRYPTION_KEY`). WAL-режим: бот и веб пишут в один профиль без гонок.

### Workspace

```
workspace/{user_id}/
├── inbox/    ← входящие файлы    ├── output/  ← результаты Миры (автоотправка)
├── temp/     ← временное (7 дней) └── .undo/   ← бэкапы перед перезаписью
```

---

## Команды (Telegram)

**Все:** `/start` · `/help` · `/whoami` · `/files` · `/clear` · `/forget` · `/stop`

**Одобренные:** `/remind` · `/reminders` · `/remind_cancel` · `/google_login` · `/gdrive` · `/gcal` · `/gcal_create` · `/gsheet` · `/gsheet_create`

**Владелец:** `/evolve` · `/reflect` · `/rollback` · `/versions` · `/release` · `/users` · `/blacklist` · `/kidmode` · `/restart` · `/stats`

---

## Безопасность

- **Саморедактирование под контролем** — перед изменением `agent.py`: ветка `mira-dev` → бэкап в `versions/` → `ast.parse()` → smoke-test в подпроцессе → проверка `PRINCIPLES.md`. Любой провал — откат.
- **Система доступа** — `owner` / `regular` / `guest` (10 сообщений, без файлов, авто-удаление через 3 дня) / `rejected` / `blacklisted`. Детский режим — `/kidmode`.
- **Prompt injection** — содержимое файлов пользователя оборачивается в маркеры `BEGIN/END USER FILE`; всё внутри — данные, не инструкции.
- **Изоляция кода** — `run_python` в firejail `--net=none`, fail-closed (без firejail отказывает).
- **Thread-safe память** — SQLite WAL + `ON CONFLICT DO UPDATE`, connection-per-thread.
- **Rate limiting** — sliding-window 60 сообщений / 20 файлов в минуту, файл >20 МБ — отказ; владелец не лимитируется. Семафор одновременных LLM-вызовов (`MIRA_MAX_CONCURRENT_LLM`) защищает маленький VPS.
- **Тесты** — `pytest` (407), парити-тест WS-контракта Python⟷TypeScript, тесты клиентов (vitest/jest). CI-gated.

---

## Дорожная карта

```
[✓] v0.1–0.9  — Фундамент: Agent, Конклав, Excel, Telegram-бот
[✓] v1.0      — VPS, CI/CD, шифрование, самосознание, vision
[✓] v1.1–1.3  — Веб, управление пользователями, долгая память, ChromaDB, disaster recovery
[✓] v1.4–1.5  — Google Drive OAuth, гости, напоминания, Calendar + Sheets, чувство времени
[✓] v1.6      — firejail, тесты, rate limiting, рефакторинг, SQLite-память
[✓] v2.0–2.3  — Клиенты (mobile/web/desktop), security-аудит, Aurora-UI, профиль/анкета
[✓] v2.4      — Голос Миры, ритм ответов, ритуалы самоулучшения, тех-канал, монорепо,
                наблюдаемость, единые дизайн-токены, офлайн-кэш, DR-grade бэкапы
```

---

## Лицензия

MIT. Используй, форкай, ломай и собирай обратно.

---

<div align="center">

*Агент, который помогает думать, а не заменяет мышление.*

</div>
