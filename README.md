<div align="center">

# 🌟 Mira

### ИИ-агент с памятью, Конклавом и Telegram-интерфейсом

[![Version](https://img.shields.io/badge/version-1.6-brightgreen?style=for-the-badge)](https://github.com/Glombert/Mira_BOT)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Claude](https://img.shields.io/badge/Claude-Sonnet_4.6-D97757?style=for-the-badge)](https://anthropic.com)
[![DeepSeek](https://img.shields.io/badge/DeepSeek-V4_Pro-4F46E5?style=for-the-badge)](https://deepseek.com)
[![Gemini](https://img.shields.io/badge/Gemini-Flash_1.5-4285F4?style=for-the-badge&logo=google&logoColor=white)](https://ai.google.dev)
[![OpenRouter](https://img.shields.io/badge/OpenRouter-Ready-6366F1?style=for-the-badge)](https://openrouter.ai)
[![Google Drive](https://img.shields.io/badge/Google_Drive-OAuth-34A853?style=for-the-badge&logo=googledrive&logoColor=white)](https://developers.google.com/drive)
[![Telegram](https://img.shields.io/badge/Telegram-Bot-26A5E4?style=for-the-badge&logo=telegram)](https://core.telegram.org/bots)
[![License](https://img.shields.io/badge/License-MIT-22C55E?style=for-the-badge)](LICENSE)

<br/>

> *Названа в честь звезды Мира — переменной, пульсирующей, меняющейся в яркости.*

<br/>

```
Пользователь
     │
     │  один голос, один интерфейс
     ▼
┌─────────────────────────────────────┐
│               МИРА (Альфа)          │
│  • ведёт диалог                     │
│  • держит контекст и память         │
│  • классифицирует задачи            │
│  • решает: сама или Конклав         │
└──────────────┬──────────────────────┘
               │  при сложных задачах
       ┌───────┼──────────┬──────────┐
       ▼       ▼          ▼          ▼
   [Coder]  [Scout]   [Planner]  [Editor]
       │                    │
   [Critic]           [Reviewer]
       │
  [Excel Specialist]
```

</div>

---

## Что это

Mira — агентная система с многоагентной оркестрацией, памятью пользователей, Telegram- и веб-интерфейсами. Пользователь всегда говорит с одним голосом — Мирой. Сложность скрыта внутри.

**Что умеет:**

- **Думать** — классифицирует задачи: простые решает сама, сложные передаёт Конклаву
- **Помнить** — структурированное резюме разговора (КТО/ПРОЕКТЫ/ФАКТЫ/ТЕКУЩЕЕ), профиль пользователя, **семантический поиск по всей истории** через ChromaDB
- **Искать** — веб-поиск через DuckDuckGo (ddgs, без ключей)
- **Видеть** — анализирует фото и изображения через Claude Vision
- **Работать с файлами** — читает, пишет, обрабатывает Excel; workspace изолирован на каждого пользователя; синхронизация с Google Drive
- **Работать с Google Календарём** — просмотр, создание событий, быстрое добавление через естественный язык (`gcal_list`, `gcal_create`, `gcal_quick_add`)
- **Работать с Google Таблицами** — чтение, запись, создание таблиц (`gsheet_read`, `gsheet_write`, `gsheet_create`)
- **Напоминать** — отложенные напоминания: Мира САМА пишет пользователю в Telegram в заданное время (`schedule_reminder`, `list_reminders`, `cancel_reminder`)
- **Запускать код** — Python в подпроцессе с изоляцией через firejail (`--net=none`)
- **Защищаться от перегрузки** — sliding-window rate limit (60 сообщ/мин, 20 файлов/мин); Мира предупреждает голосом, а не молчит
- **Резервироваться** — при сбое одного LLM-провайдера переключается на следующий по цепочке (OpenRouter → DeepSeek direct → Anthropic direct)
- **Понимать себя** — читает собственный код и конфиги (`list_self`, `read_self`), смотрит историю изменений (`git_log`), обновляет персону через `write_persona`
- **Создавать агентов** — `write_agent_config` записывает конфиг в `agents/`, валидирует, создаёт бэкап, уведомляет владельца
- **Управлять пользователями** — guest/regular/rejected/blacklisted, уведомления с кнопками, карточки
- **Меняться безопасно** — `/evolve` предлагает diff, проверяет принципы, делает бэкап, требует подтверждения; счётчик успешных эволюций
- **Работать через веб** — FastAPI + WebSocket интерфейс с Telegram Login Widget, загрузкой файлов и полным доступом к Конклаву
- **Знать время** — осознаёт текущую дату и время, не теряется в хронологии

Всего **28 инструментов**: `list_files`, `read_file`, `write_file`, `run_python`, `excel_read`, `excel_write`, `save_template`, `list_templates`, `list_self`, `recall`, `git_log`, `read_self`, `write_persona`, `write_agent_config`, `web_search`, `gdrive_list`, `gdrive_read`, `gdrive_write`, `gcal_list`, `gcal_create`, `gcal_quick_add`, `gsheet_read`, `gsheet_write`, `gsheet_create`, `schedule_reminder`, `list_reminders`, `cancel_reminder`, `metrics_read`.

---

## Быстрый старт

### Локальная разработка

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
OWNER_CLI_USER=andrey
```

Запуск для разработки:

```bash
python telegram_bot.py              # Telegram Bot
python web/app.py                   # Веб-интерфейс (порт 8000)
python agent.py --profile dev --user andrey   # CLI
```

### Развёртывание на VPS

**1. Клонируй и установи зависимости:**
```bash
git clone https://github.com/Glombert/Mira_BOT.git mira_agent
cd mira_agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**2. Настрой `.env`** (аналогично локальному).

**3. Восстанови память из облака (если переезд):**
```bash
rclone copy gdrive:Mira/memory ./memory
```

**4. Создай systemd-сервисы** — `mira-bot` (Telegram) и `mira-web` (FastAPI):

`/etc/systemd/system/mira-bot.service`:
```ini
[Unit]
Description=Mira AI Bot (Telegram)
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/mira_agent
ExecStart=/root/mira_agent/venv/bin/python telegram_bot.py
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/mira-web.service`:
```ini
[Unit]
Description=Mira Web Interface
After=network.target

[Service]
Type=simple
WorkingDirectory=/root/mira_agent
ExecStart=/root/mira_agent/venv/bin/python web/app.py
Restart=on-failure
RestartSec=5s

[Install]
WantedBy=multi-user.target
```

```bash
systemctl daemon-reload
systemctl enable --now mira-bot mira-web
```

**5. Настрой автодеплой (GitHub Actions):**

В настройках репозитория добавь три секрета: `SSH_PRIVATE_KEY`, `VPS_HOST`, `VPS_USER`.
Файл `.github/workflows/deploy.yml` уже в репозитории — при каждом пуше в `main` сервер обновляется автоматически.

**6. Nginx + SSL (DuckDNS + acme.sh):**
```bash
# Получить бесплатный субдомен на duckdns.org, затем:
curl https://get.acme.sh | sh -s email=your@email.com
export DuckDNS_Token="токен_с_duckdns.org"
~/.acme.sh/acme.sh --issue --dns dns_duckdns -d your-name.duckdns.org --server letsencrypt
mkdir -p /etc/ssl/mira
~/.acme.sh/acme.sh --install-cert -d your-name.duckdns.org \
  --fullchain-file /etc/ssl/mira/fullchain.cer \
  --key-file /etc/ssl/mira/key.key \
  --reloadcmd "systemctl reload nginx"
# Шаблон Nginx конфига: scripts/nginx.conf.example
cp scripts/nginx.conf.example /etc/nginx/sites-available/mira
# Замени YOUR_DOMAIN, запусти: nginx -t && systemctl start nginx
```

**7. Настрой бэкап памяти:**

`/root/mira_backup.sh` синхронизирует `memory/` (профили, сессии, рефлексии) и `versions/` (бэкапы кода и персоны) на Drive ежедневно в 3:00 UTC:
```bash
cat > /root/mira_backup.sh << 'EOF'
#!/bin/bash
LOG=/root/mira_backup.log
echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) backup ===" >> $LOG
rclone sync /root/mira_agent/memory   gdrive:Mira/memory   --log-file=$LOG
rclone sync /root/mira_agent/versions gdrive:Mira/versions --log-file=$LOG
EOF
chmod +x /root/mira_backup.sh
echo "0 3 * * * /root/mira_backup.sh" | crontab -
```

**8. Зашифруй `.env` на Drive** (без него зашифрованная память бесполезна):
```bash
# Придумай и сохрани пароль в менеджере паролей — он понадобится для восстановления
BACKUP_PASSPHRASE='ТВОЙ_ПАРОЛЬ' /root/mira_agent/scripts/backup_env.sh
```

Перезапускай после любых правок `.env` — например смены ключей API.

---

## Disaster Recovery

Полный перенос Миры на новый сервер.

**Что нужно сохранить** (за пределами сервера):
- Парольная фраза от `backup_env.sh` — в менеджере паролей или на бумаге
- Доступ к Google Drive аккаунту (там зашифрованная память, .env и бэкапы кода)

**Восстановление:**

```bash
# 1. Поставь зависимости и rclone, настрой Drive remote 'gdrive:'
apt install -y python3.12 python3.12-venv rclone gpg firejail
rclone config   # настрой gdrive: интерактивно

# 2. Клонируй код
git clone https://github.com/Glombert/Mira_BOT.git /root/mira_agent
cd /root/mira_agent
python3 -m venv venv && venv/bin/pip install -r requirements.txt

# 3. Восстанови зашифрованный .env
BACKUP_PASSPHRASE='ТВОЙ_ПАРОЛЬ' ./scripts/restore_env.sh

# 4. Восстанови память и историю изменений
rclone copy gdrive:Mira/memory   ./memory
rclone copy gdrive:Mira/versions ./versions

# 5. Запусти systemd-сервисы
systemctl daemon-reload
systemctl enable --now mira-bot mira-web
```

После этого Мира на новом сервере знает всех пользователей, помнит прошлые разговоры, сохранила свои рефлексии и видит свою историю эволюции.

---

## Архитектура

### Конклав — многоагентная оркестрация

```
Роутер классифицирует запрос
    │
    ├─ chat/files → Мира отвечает сама (1 вызов API)
    │
    ├─ search → Scout (без Редактора — быстрее)
    │
    └─ code/complex → Конклав
           │
           ├─ Scout || Coder — параллельно на первой итерации (complex)
           ├─ Editor   — улучшает результат (только для code/complex)
           └─ Critic   — проверяет (0–10, принимаем при ≥7)
```

Максимум 3 итерации. Если critic ставит ≥7/10 — принимаем раньше.
При стагнации (оценка не растёт 2 итерации) — возвращаем лучший результат.
Для search-задач Редактор пропускается — экономия одного LLM-вызова.
Для complex-задач Scout и Coder запускаются параллельно через ThreadPoolExecutor.

Мира ведёт пользователя через процесс: каждый шаг Конклава сопровождается коротким сообщением `💭`.

### Один класс — разные конфиги

Все агенты — один класс `Agent`, разные JSON в `agents/`:

```
agents/
  alpha.json              ← Мира, голос системы
  coder.json              ← код (Claude Sonnet 4.6 → Opus 4.7 → Anthropic direct)
  planner.json            ← декомпозиция задач
  editor.json             ← редактура (DeepSeek)
  critic.json             ← контроль качества (Gemini → Claude)
  reviewer.json           ← финальная проверка
  scout.json              ← веб-поиск (Perplexity sonar-pro → DuckDuckGo)
  excel_specialist.json   ← работа с таблицами
  _template.json          ← базовый шаблон
```

### Резервирование провайдеров

```json
{
  "model_chain": [
    { "provider": "openrouter", "model": "anthropic/claude-sonnet-4.6" },
    { "provider": "openrouter", "model": "deepseek/deepseek-chat" },
    { "provider": "anthropic",  "model": "claude-sonnet-4.6" }
  ]
}
```

При сбое первого — переход ко второму. Каждое переключение пишется в `memory/decisions.log` и уведомляет владельца в Telegram.

### Память

```
memory/
├── mira.db                 ← SQLite (WAL): профили, сессии, напоминания,
│                            рефлексии, gdrive-токены
├── chroma/                 ← векторная база ChromaDB (семантический поиск)
├── templates/              ← пользовательские шаблоны задач
└── decisions.log           ← лог переключений провайдеров и решений
```

Все пользовательские данные в `mira.db` прозрачно шифруются Fernet (если задан `MEMORY_ENCRYPTION_KEY`). `decisions.log` не шифруется (технический, без личных данных).

WAL-режим позволяет Telegram-боту и веб-интерфейсу писать в один профиль одновременно без гонок. До v1.6 каждый компонент имел свой JSON-файл и обновления могли затирать друг друга.

Миграция со старого формата: `python -m tools.migrate_state` — читает JSON-файлы и переносит в mira.db, идемпотентно.

Бэкап: `rclone sync memory/ gdrive:Mira/memory` — настраивается через cron.

### Логи

```
logs/
├── agent.log               ← текущий день
├── agent.log.2026-05-11    ← вчера
└── agent.log.2026-05-10    ← позавчера (старше 3 дней удаляется)
```

Ротация ежедневная, хранится 3 дня. Логи — не память: профили и сессии в `memory/`.

### Workspace

```
workspace/{user_id}/
├── inbox/    ← сюда отправляй файлы боту
├── output/   ← сюда Мира кладёт результаты (автоотправка в Telegram)
├── temp/     ← временное, чистится через 7 дней
└── .undo/    ← бэкапы перед перезаписью
```

---

## Команды

### Telegram (все пользователи)

| Команда | Что делает |
|---|---|
| `/start` | Начать / онбординг |
| `/help` | Справка и меню кнопок |
| `/whoami` | Мой профиль |
| `/files` | Мои файлы (inbox / output) |
| `/clear` | Очистить историю диалога |
| `/forget` | Сбросить профиль и историю |
| `/stop` | Остановить Конклав |

### Telegram (одобренные пользователи)

| Команда | Что делает |
|---|---|
| `/remind <ISO-дата> <текст>` | Создать напоминание (Мира напишет в указанное время) |
| `/reminders` | Список активных напоминаний |
| `/remind_cancel <id>` | Отменить напоминание |
| `/google_login` | Привязать Google Drive (получить ссылку) |
| `/google_auth <url>` | Завершить привязку Google Drive |
| `/google_logout` | Отвязать Google Drive |
| `/gdrive` | Список файлов на Google Drive |
| `/gdrive_get <имя>` | Скачать файл с Google Drive |
| `/gdrive_toggle` | Вкл/выкл авто-загрузку файлов на Drive |
| `/gcal [N]` | Ближайшие N событий из Google Календаря |
| `/gcal_create <текст>` | Создать событие через естественный язык |
| `/gsheet <id>` | Прочитать Google Таблицу |
| `/gsheet_create <название>` | Создать Google Таблицу |

### Telegram (только владелец)

| Команда | Что делает |
|---|---|
| `/evolve <задача>` | Изменить код агента (diff + кнопки подтверждения) |
| `/reflect` | Агент читает и анализирует свой код |
| `/rollback` | Откат `agent.py` на предыдущую версию |
| `/versions` | Список резервных копий |
| `/release` | Смержить `mira-dev` в `main` |
| `/git [msg]` | Закоммитить изменения |
| `/users` | Управление пользователями (inline-кнопки) |
| `/blacklist` | Чёрный список |
| `/kidmode <id> on\|off` | Детский режим для пользователя |
| `/restart` | Перезапустить бота |
| `/evolution_count` | Статистика попыток самосовершенствования |

### CLI (разработчик)

```bash
python agent.py --profile dev --user andrey
```

Те же команды через `/` в терминале. Плюс `/cloud sync`, `/rollback`, `/versions`.

---

## Безопасность

### Саморедактирование под контролем

Перед любым изменением `agent.py`:
1. Переключение на ветку `mira-dev`
2. Бэкап в `versions/`
3. Проверка синтаксиса через `ast.parse()`
4. Smoke-test в подпроцессе (`--self-test`)
5. Проверка `PRINCIPLES.md` — конституция агента

Если хоть один шаг не прошёл — изменения не применяются.

### Система доступа

| Статус | Возможности |
|---|---|
| `owner` | Всё, включая `/evolve`, `/release`, управление пользователями |
| `regular` | Полный доступ к workspace, инструментам, Google Drive (опционально) |
| `guest` | Только диалог (Gemini Flash), 10 сообщений, без файлов, ждёт одобрения |
| `rejected` | Отклонён, история сохранена |
| `blacklisted` | Ничего, уведомление владельцу раз в сутки |

Гости авто-удаляются через 3 дня без одобрения.

**Детский режим** — `/kidmode <user_id> on` включает для конкретного пользователя ограниченный системный промпт: простой язык, фильтр взрослых тем. Telegram возраст не передаёт — включается вручную владельцем.

### Защита от prompt injection

Содержимое файлов пользователя оборачивается в маркеры:
```
--- BEGIN USER FILE: filename.txt ---
содержимое
--- END USER FILE ---
```
Всё между маркерами — данные, не инструкции.

### Thread-safe память

SQLite в WAL-режиме плюс `ON CONFLICT DO UPDATE` дают атомарный upsert: одновременные записи из telegram-бота и веба сериализуются на уровне БД, никто никого не затирает. Connection-per-thread через `threading.local`.

### Rate limiting

Sliding-window лимит на пользователя:
- 60 сообщений в минуту
- 20 файлов в минуту
- Файл больше 20 МБ — отказ с пояснением

При превышении Мира отвечает в своём голосе («помедленнее, я ещё не успеваю отвечать»), а не молчит и не падает с 429. Владелец (`OWNER_TELEGRAM_ID`) не лимитируется.

### Тесты

`pytest tests/` — 56 тестов критических путей: session token HMAC, path traversal, безопасные filenames, CRUD профилей через SQLite, sliding-window rate limit, миграция state. Запускаются автоматически в CI; локально — изолированы (`isolated_cwd` создаёт временную базу под каждый тест).

---

## Стек

| Компонент | Технология | Статус |
|---|---|---|
| Язык | Python 3.12+ | ✓ |
| LLM | OpenRouter + Anthropic direct + DeepSeek direct | ✓ |
| Telegram | python-telegram-bot 22+ | ✓ |
| Веб | FastAPI + WebSocket + Telegram Login Widget | ✓ |
| Vision | Claude Sonnet 4.6 (фото в чате и веб) | ✓ |
| Excel | openpyxl | ✓ |
| Поиск | Perplexity sonar-pro → DuckDuckGo (ddgs) | ✓ |
| Изоляция кода | firejail `--net=none` | ✓ |
| Шифрование | Fernet (mira.db), GPG (.env на Drive) | ✓ |
| Память | SQLite WAL (mira.db) + структурированное резюме + ChromaDB (семантика) | ✓ |
| Google Drive | OAuth 2.0 (личный аккаунт пользователя) + rclone (бэкап памяти) | ✓ |
| Google Calendar | API (gcal_list, gcal_create, gcal_quick_add) | ✓ |
| Google Sheets | API (gsheet_read, gsheet_write, gsheet_create) | ✓ |
| Напоминания | таблица reminders в mira.db + фоновая проверка каждые 30с | ✓ |
| Rate limit | sliding window (60 msg / 20 files в минуту, owner exempt) | ✓ |
| Тесты | pytest, 56 тестов критических путей | ✓ |
| Логи | TimedRotatingFileHandler + Drive cron | ✓ |
| Деплой | systemd (mira-bot + mira-web) + GitHub Actions CI/CD | ✓ |
| VPS | mira-bot.duckdns.org (Ubuntu 24.04) | ✓ |

---

## Дорожная карта

```
[✓] v0.1–0.9  — Фундамент, Agent, Конклав, Excel, Telegram Bot
[✓] v1.0      — VPS, CI/CD, шифрование, самосознание, vision, деплой
[✓] v1.1      — Веб-интерфейс, управление пользователями, долгая память, Drive sync
[✓] v1.2      — Живой голос в Конклаве, переработанная персона, git_log, UX-полировка
[✓] v1.3      — Семантическая память (ChromaDB), disaster recovery, отдельные reflections
[✓] v1.4      — Google Drive OAuth (личные аккаунты пользователей), гости на Gemini Flash
[✓] v1.5      — Напоминания (scheduled reminders), Google Calendar + Sheets, web-паритет, чувство времени, ускорение Конклава
[✓] v1.6      — firejail, тесты (56 шт), rate limiting, рефакторинг agent.py (2460→1725 строк), SQLite миграция memory/
```

---

## Лицензия

MIT. Используй, форкай, ломай и собирай обратно.

---

<div align="center">

*Агент, который помогает думать, а не заменяет мышление.*

</div>
