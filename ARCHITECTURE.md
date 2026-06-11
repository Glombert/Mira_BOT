# Mira — Архитектура системы

> Статус: production на `mira-bot.duckdns.org` (VPS Амстердам).
> Обновлено: 2026-06-11. Источник версии — бейдж в `README.md`.

Этот документ — карта системы «как она устроена сейчас». Историю изменений
смотри в `WHATS_NEW.md`, правила поведения Миры — в `RULES.md`/`behavior.md`,
рабочие правила для агентов-разработчиков — в `CLAUDE.md`.

---

## Концепция

Пользователь всегда говорит с одним агентом — **Альфой** (Мира). Сложность
скрыта внутри: при необходимости Альфа зовёт специалистов Конклава, но голос
наружу всегда её. Один диалог общий для всех интерфейсов (Telegram, веб,
десктоп, мобайл) — он привязан к `user_id = tg_<id>` и хранится в одной БД.

```
                 Telegram · Web · Desktop · Mobile
                          один диалог
                              │
                              ▼
                  ┌────────────────────────┐
                  │         АЛЬФА (Мира)    │
                  │  диалог, память, голос  │
                  └───────────┬─────────────┘
                              │ только на точечные задачи
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
          [Coder]        [Scout]         [Planner] … (Конклав)
```

---

## Карта репозитория

```
mira_agent/
├── agent.py            класс Agent + загрузка персоны; CLI-вход; мишень /evolve
├── telegram_bot.py     entrypoint бота (main + регистрация хендлеров)
│
├── core/               ЯДРО
│   ├── providers.py        LLM-провайдеры, failover-цепочка, prompt caching
│   ├── conclave.py         оркестратор Конклава (executor→editor→critic)
│   ├── router.py           классификация задачи (сама / Конклав)
│   ├── agent_tools.py      реестр 40 инструментов + execute_tool
│   ├── memory_manager.py   суммаризация истории, обновление профиля
│   └── memory_crypto.py    Fernet-шифрование памяти
│
├── bot/                TELEGRAM-СЛОЙ
│   ├── chat.py             handle_message + онбординг
│   ├── callbacks.py        inline-кнопки
│   ├── files.py            входящие документы и фото
│   ├── commands_user.py    команды для всех (вход, Google, напоминания)
│   ├── commands_owner.py   owner: evolve/reflect, статистика, юзеры
│   ├── commands_tasks.py   /task, /tz, /rename, ритуалы
│   ├── background.py       heartbeat, циклы напоминаний и ритуалов
│   ├── helpers.py          сессии, профили, отправка сообщений
│   ├── menu.py, config.py  меню команд, конфиг+логирование
│
├── web/                FASTAPI + WEBSOCKET
│   ├── app.py              HTTP-роуты + WS-цикл чата
│   ├── ws_commands.py      WS type=command (≈40 веток меню/панелей)
│   ├── ws_protocol.py      pydantic-контракт ⟷ TS (источник истины)
│   ├── sessions.py         сессии, системный промпт, профиль, анкета
│   ├── alpha.py            запуск агента из веб-слоя
│   ├── ritual_runner.py    фоновые ритуалы и шедул-задачи
│   ├── panels.py           данные экранов (сайдбар, бэкапы, карточки памяти)
│   ├── deps.py, security.py сессии (HMAC), безопасность
│   ├── meta.py             версия из README-бейджа
│   └── routes/             вынесенные роутеры (mobile, files, owner_inbox)
│
├── tools/              ИНСТРУМЕНТЫ (Google, файлы, память, логи, мониторинг…)
│   ├── tool_schemas.py     JSON-схемы инструментов для function calling
│   ├── server_health.py    здоровье сервера + сэмплер метрик
│   ├── vpn_tools.py        мониторинг WireGuard и РУ-моста
│   ├── model_watch.py      дифф каталога моделей (ритуал agent_versions)
│   ├── rituals.py          загрузка ритуалов + RITUAL_HANDLERS
│   ├── paths.py            якорь PROJECT_ROOT (пути не зависят от cwd)
│   └── …                   db, gdrive, scheduler, semantic_memory, …
│
├── agents/*.json       конфиги агентов Конклава (один класс, разные модели)
│   └── rituals/*.json      фоновые задачи (cron + on_startup / handler)
├── profiles/*.json     права пользователей (default / dev / guest)
├── clients/            npm-воркспейсы: apps/web (Next.js), apps/desktop (Tauri)
├── mobile/             React Native (APK через CI → репо Mira_Mobile)
├── tests/              pytest (453+), парити-тест WS-контракта
├── scripts/            деплой, бэкап, релиз, wg_add_peer, smoke
└── memory/             оперативные данные (mira.db, chroma, overlay) — git-ignored
```

---

## Поток запроса (веб)

```
браузер ──WS /ws──▶ web/app.py:chat()
                      │  verify_session (HMAC)
                      │  собрать системный промпт (web/sessions.py)
                      ▼
                 web/alpha.py:_invoke_alpha
                      │  router.classify → сама или Конклав
                      ▼
                 core/providers.call(model_chain)
                      │  failover: OpenRouter → DeepSeek → …
                      ▼
                 ответ ──▶ дробление (chunking) ──▶ WS назад
                      └──▶ фон: индексация в ChromaDB, суммаризация
```

Telegram-поток аналогичен: `bot/chat.py:handle_message` → те же
`core/providers` и `core/conclave`. Сессия общая по `tg_<id>`.

---

## Три слоя промпта Миры

| Файл | Что | Self-editable |
|------|-----|---------------|
| `persona.json` | характер (curiosity, emotions, self_awareness) | да (overlay) |
| `RULES.md` | регламент поведения (канон, для людей) | нет |
| `behavior.md` | сжатая инжект-форма RULES для системного промпта | нет |
| `PRINCIPLES.md` | безопасность кода (для /evolve) | нет |

При конфликте характера и регламента — **регламент выше**. Правки Миры о себе
идут в `memory/persona_overlay.json` (git-untracked), база `persona.json`
остаётся стабильным шаблоном — деплой `git pull` не конфликтует.

---

## Память

- **Сессии** (`tools/db.py`): `user_id = tg_<id>`, веб и Telegram делят одну.
- **Семантическая** (`tools/semantic_memory.py`, ChromaDB): scoped по user_id,
  подмешивается в промпт только при близком совпадении + кулдаун.
- **Шифрование**: при заданном `MEMORY_ENCRYPTION_KEY` сессии шифруются Fernet
  (fail-closed — сбой крипты не пишет открытый текст).

---

## Фоновые задачи (ритуалы)

`agents/rituals/*.json` — cron + промпт (или `handler` для скриптов без LLM).
Выполняются в `bot/background.py`, доставка через `web/ritual_runner.py`:
`owner_inbox` + WS-push канала `tech` + Telegram при `IMPORTANCE >= threshold`.

| Ритуал | Тип | Расписание |
|--------|-----|-----------|
| `server_health` | handler (без LLM) | ежедневно 00:00 |
| `agent_versions` | гибрид: скрипт-дифф → LLM | 1 и 15 числа, 09:00 |
| `log_audit` | LLM | 1 и 15 числа, 22:00 |
| `self_review` | LLM (Opus) | 1 и 15 числа, 21:00 |
| `weekly_summary` | LLM | 1 и 15 числа, 09:00 |

---

## Инфраструктура

- **VPS Амстердам** (`85.137.89.79`, FirstVDS): два systemd-сервиса
  `mira-bot` и `mira-web` (отдельные процессы), общая БД `memory/mira.db`,
  nginx + WireGuard + Reality-контейнер.
- **РУ-мост** (`5.42.98.236`, Timeweb): nftables-релей. Домашний роутер и
  VPN-клиенты коннектятся к РУ-IP (ТСПУ душит прямой иностранный UDP), мост
  DNAT'ит трафик на Амстердам (UDP 51820 → WireGuard, TCP 443 → Reality).
- **Мониторинг**: сэмплер раз в 5 мин пишет RAM/load/disk и per-peer трафик
  WireGuard в SQLite (retention 7 дней) → owner-экраны «Сервер» и «VPN».
- **Деплой**: `git pull origin mira-dev` + `scripts/deploy_web.sh` (билд
  Next.js) + `systemctl restart`. Мобайл — `mobile/scripts/release.sh` (CI→APK).

---

## Провайдеры LLM

`core/providers.py` — цепочка с failover и семафором конкурентности. Основная
у Альфы: `anthropic/claude-sonnet-4.6` (OpenRouter) → `deepseek-v4-pro`
(DeepSeek напрямую). Пустой баланс OpenRouter (402) не валит Миру — это
retriable-ошибка, идёт переключение на резерв. Статичное ядро системного
промпта кэшируется (prompt caching Anthropic).
