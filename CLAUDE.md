# CLAUDE.md — рабочие правила для агентов в этом репо

Этот файл читается Claude Code в начале каждой сессии. Здесь — **обязательные**
рабочие правила, выработанные владельцем за время разработки Миры. Если правило
здесь конфликтует с общими привычками — побеждает то, что здесь.

---

## 1. Архитектура одной строкой

Mira — личный AI-ассистент. **Две кодовые базы:**

- **`Mira_BOT` (этот репо)** — Python-бэк (FastAPI + python-telegram-bot) и
  веб/desktop-клиент (Next.js + Tauri в `clients/`).
- **`Mira_Mobile` (отдельный репо)** — React Native APK для Android.
  https://github.com/Glombert/Mira_Mobile

Прод: VPS `root@mira-bot.duckdns.org`, два systemd-сервиса (`mira-bot`,
`mira-web`), отдельные процессы, общая БД SQLite (`memory/db.sqlite3`).

---

## 2. Ветка и деплой

- Работаем в **`mira-dev`**, **не в `main`**. Это рабочая ветка прода.
- Деплой Mira_BOT на VPS: `git pull origin mira-dev` + `bash scripts/deploy_web.sh`
  (билдит Next.js) + `systemctl restart mira-bot` (бот ребутается сам нечасто,
  но веб иногда нужно вместе с ботом).
- Деплой Mira_Mobile: `scripts/release.sh X.Y.Z --notes "..."` —
  это **bump version + commit + push + ждёт CI + публикует GitHub Release с APK**.
  `/mobile/version` берёт латест из релизов автоматически, приложение видит и
  предлагает обновиться.

## 3. НЕ ДЕЛАТЬ локально

- **Никакие тяжёлые сборки локально** — gradle, native Android, любой
  `react-native run-android`. Кладёт ноут владельца. Только через CI.
- **Не пушить в `main`** Mira_BOT. Деплой только из `mira-dev`.
- **Не трогать UFW на VPS** — там WireGuard на UDP 51820, ufw ломает доступ.
- **Не терять `MEMORY_ENCRYPTION_KEY`** в `.env` на VPS — потеря = потеря
  всей зашифрованной памяти пользователей.

## 4. Тесты обязательны

Перед коммитом — `venv/bin/pytest -q`. Сейчас базовый зелёный счёт ~270+
тестов. Если падает — **не коммитим**, фиксим. Тесты падают только если фикс
сам всё чинит, **никогда** не маркируем как `skip` чтобы пройти.

## 5. WHATS_NEW.md — журнал новых фич

**Каждая новая фича** (не багфикс) → запись в начало `WHATS_NEW.md` под
сегодняшней датой с пометкой `[ALL]` или `[OWNER]`. Мира читает этот файл
через инструмент `whats_new()` и сама рассказывает пользователям, когда
уместно. **Багфиксы туда не пишем** — только новые возможности.

Формат:
```
## 2026-MM-DD
- [ALL] **Название**: одно-два предложения по делу.
- [OWNER] **Только владельцу**: ...
```

## 6. README в обоих репо

Когда добавили заметную фичу — обнови строку про неё в README. Для
**Mira_Mobile** обновляй README в его репо (отдельно от Mira_BOT) — мобайл
живёт в `https://github.com/Glombert/Mira_Mobile`.

## 7. Архитектура промпта Миры

**Три слоя**, каждый в своём файле:
- `persona.json` — **характер** (self-editable: curiosity, emotions,
  self_awareness, reflections). Мира может писать сюда через `write_persona`.
- `RULES.md` — **регламент поведения** (для людей, канон). Не self-editable.
- `behavior.md` — **сжатая инжект-форма RULES** для системного промпта.
  При изменении RULES синхронизируй behavior.md тоже.
- `PRINCIPLES.md` — **безопасность кода** (для `/evolve`). Только Мира-Evolve.

При конфликте характера и регламента — **регламент выше**.

## 8. Технический канал владельца (tech-mode)

Mira_BOT v2.4+ имеет отдельный канал в приложении: `owner_inbox` (SQLite,
retention 30 дней), WS-push с `channel='tech'`, отдельная сессия
`tech_<owner_id>`. Двусторонний разговор в роли разработчика — через
`mode='tech'` в WS-сообщении + `Agent.run(extra_system=...)`.

Эндпоинты: `GET/POST /m/owner_inbox`, `GET /history?scope=tech` (owner-only).

## 9. Ритуалы

`agents/rituals/*.json` — фоновые задачи с cron + `on_startup` флагом.
- Выполняются в `telegram_bot.py:_ritual_loop` (отдельный поток).
- Защита от дублей: in-memory `running` set (LLM-вызов может занять > 60s,
  без флага следующая итерация цикла запускает повторно).
- Доставка: `web/app.py:_run_ritual_background` пишет в `owner_inbox` + WS
  push + Telegram fallback (только если `IMPORTANCE >= notify_threshold`).
- Дробление Telegram на чанки 3900 (полный текст всегда в БД).

Добавить новый ритуал: создать JSON с `name/schedule/prompt/agent/owner_only/notify_threshold/on_startup`.

## 10. Память пользователя

- **Сессии** (`db.load_session/save_session`): user_id = `tg_<id>` (web и tg
  делят одну сессию по этому ключу).
- **Семантическая память** (`tools/semantic_memory.py`, ChromaDB): scoped по
  user_id (`where={user_id}`), кросс-юзер-утечек нет.
- **Recall в промпт**: `format_for_prompt` подмешивает только при
  `max_distance=0.35` и кулдауне (карточка «Из памяти» раз в 6+ сообщений).
- **Шифрование**: если `MEMORY_ENCRYPTION_KEY` задан — сессии шифруются
  Fernet. Тесты используют `_close_thread_conn` фикстуру и `monkeypatch`
  на `DB_PATH`.

## 11. Self-editable persona — грабли деплоя

Mira пишет в `persona.json` через `write_persona`. На проде `git pull` упадёт
с конфликтом, если Мира изменила файл между деплоями. **При деплое: либо
сделать `git checkout -- persona.json` перед pull (потеряем эволюцию), либо
вручную перенести её правки в репозиторную версию и коммитнуть до pull.**
Долгосрочный TODO: вынести self-editable поля (curiosity/emotions/
self_awareness) в git-untracked overlay-файл `memory/persona_overlay.json`.

## 12. Стиль ответов Миры (если будешь править поведение)

- **Дробление на 2-3 сообщения** (`tools/chunking.py:split_for_chat`):
  длинные ответы → реакция / основа / эпилог. Код-блоки и таблицы не дробятся.
- **Активный залог, женский род**, разговорный регистр.
- **Без AI-клише и канцелярита** — список запрещённого в `behavior.md`.
- **Не отвечать от лица «исполнителей»**: Конклав — её инструменты, голос
  всегда её.
- **Не спрашивать то, что знаем**: имя, год, часовой пояс берутся из
  профиля.

## 13. Чего избегать в коде

- Не делать **бэквард-компат для удалённых вещей** (комментарии
  «// removed», переименование на `_var` и т.п.) — удаляем полностью.
- Не писать комментарии, объясняющие **что** делает код. Только **почему**,
  если это не очевидно (скрытая инвариант, известный bug-workaround).
- Не добавлять `try/except` "на всякий случай" — только на реальных границах
  (внешние API, IO). Внутреннему коду доверяем.
- Не использовать `--no-verify` / `--no-gpg-sign` в git, если владелец не
  попросил.

## 14. Внешние URL и сервисы

- `https://mira-bot.duckdns.org` — прод-домен, фронт + WS + API.
- `https://github.com/Glombert/Mira_BOT` — этот репо.
- `https://github.com/Glombert/Mira_Mobile` — мобайл, приватный.
- `https://api.telegram.org` — Telegram bot API (токен в `.env`).
- OpenRouter, OpenAI, Anthropic, DeepSeek — провайдеры LLM
  (`tools/providers.py`).

## 15. Если что-то непонятно

В корне есть `README.md` с актуальной картой возможностей и архитектурой.
`memory/` — оперативный архив (не редактировать без необходимости).
`docs/` — длинные документы. `agent.log` — лог-файл бота локально.
