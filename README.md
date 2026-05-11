<div align="center">

# 🌟 Mira

### ИИ-агент с памятью, Конклавом и Telegram-интерфейсом

[![Version](https://img.shields.io/badge/version-1.3-brightgreen?style=for-the-badge)](https://github.com/Glombert/Mira_BOT)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![Claude](https://img.shields.io/badge/Claude-Sonnet_4.6-D97757?style=for-the-badge)](https://anthropic.com)
[![OpenRouter](https://img.shields.io/badge/OpenRouter-Ready-6366F1?style=for-the-badge)](https://openrouter.ai)
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
   [Coder]  [Planner]  [Critic]  [Scout]
               │
          [Editor] [Reviewer]
```

</div>

---

## Что это

Mira — агентная система с многоагентной оркестрацией, памятью пользователей и Telegram-интерфейсом. Пользователь всегда говорит с одним голосом — Мирой. Сложность скрыта внутри.

**Что умеет:**

- **Думать** — классифицирует задачи: простые решает сама, сложные передаёт Конклаву
- **Помнить** — структурированное резюме разговора (КТО/ПРОЕКТЫ/ФАКТЫ/ТЕКУЩЕЕ), профиль пользователя, **семантический поиск по всей истории** через ChromaDB
- **Искать** — веб-поиск через Perplexity (приоритет) или DuckDuckGo (без ключей)
- **Видеть** — анализирует фото и изображения через Claude Vision
- **Работать с файлами** — читает, пишет, обрабатывает Excel; workspace изолирован на каждого пользователя; синхронизация с Google Drive
- **Запускать код** — Python в подпроцессе с изоляцией через firejail
- **Резервироваться** — при сбое одного LLM-провайдера переключается на следующий по цепочке
- **Понимать себя** — читает собственный код и конфиги (`list_self`, `read_self`), смотрит историю изменений (`git_log`), обновляет персону через `write_persona`
- **Управлять пользователями** — guest/regular/rejected/blacklisted, уведомления с кнопками, карточки
- **Меняться безопасно** — `/evolve` предлагает diff, проверяет принципы, делает бэкап, требует подтверждения; счётчик успешных эволюций

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
python telegram_bot.py          # Telegram Bot
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

**4. Создай systemd-сервис** `/etc/systemd/system/mira-bot.service`:
```ini
[Unit]
Description=Mira AI Bot
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

```bash
systemctl daemon-reload
systemctl enable mira-bot
systemctl start mira-bot
```

**5. Настрой автодеплой (GitHub Actions):**

В настройках репозитория добавь три секрета: `SSH_PRIVATE_KEY`, `VPS_HOST`, `VPS_USER`.
Файл `.github/workflows/deploy.yml` уже в репозитории — при каждом пуше в `main` сервер обновляется автоматически.

**6. Веб-интерфейс:**
```bash
cp scripts/mira-web.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable mira-web && systemctl start mira-web
# Добавь в .env: WEB_ACCESS_TOKEN=<случайная строка>
```

**7. Nginx + SSL (DuckDNS + acme.sh):**
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

**8. Настрой бэкап памяти:**

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

**9. Зашифруй `.env` на Drive** (без него зашифрованная память бесполезна):
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

# 5. Запусти systemd-сервисы (см. шаги 4 и 6 раздела "Развёртывание")
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
    ├─ search → Scout (Perplexity → DuckDuckGo)
    │
    └─ code/complex → Конклав
           │
           ├─ Coder    — пишет код (Claude Opus 4.7)
           ├─ Editor   — улучшает результат (DeepSeek)
           └─ Critic   — проверяет (Gemini → GPT → Claude)
```

Максимум 3 итерации. Если critic ставит ≥7/10 — принимаем раньше.

Мира ведёт пользователя через процесс: каждый шаг Конклава сопровождается коротким сообщением `💭`.

### Один класс — разные конфиги

Все агенты — один класс `Agent`, разные JSON в `agents/`:

```
agents/
  alpha.json              ← Мира, голос системы
  coder.json              ← код (Claude Opus 4.7 → Sonnet 4.6 → Anthropic direct)
  planner.json            ← декомпозиция задач
  editor.json             ← редактура (DeepSeek)
  critic.json             ← контроль качества (Gemini → GPT → Claude)
  reviewer.json           ← финальная проверка
  scout.json              ← веб-поиск (Perplexity sonar-pro → DuckDuckGo)
  excel_specialist.json   ← работа с таблицами
```

### Резервирование провайдеров

```json
{
  "model_chain": [
    { "provider": "openrouter", "model": "anthropic/claude-sonnet-4.6" },
    { "provider": "openrouter", "model": "deepseek/deepseek-chat" },
    { "provider": "anthropic",  "model": "claude-opus-4-7" }
  ]
}
```

При сбое первого — переход ко второму. Каждое переключение пишется в `memory/decisions.log`.

### Память

```
memory/
├── {user_id}.json          ← профиль пользователя
├── sessions/{user_id}.json ← история диалога
└── decisions.log           ← лог переключений провайдеров и решений
```

Бэкап: `rclone sync memory/ gdrive:Mira/memory` — настраивается через cron.

### Логи

```
logs/
├── agent.log               ← текущий день
├── agent.log.2026-05-07    ← вчера
└── agent.log.2026-05-06    ← позавчера (старше 3 дней удаляется)
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
| `/forget` | Сбросить профиль |
| `/stop` | Остановить Конклав |

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
| `regular` | Полный доступ к workspace и инструментам |
| `guest` | Только диалог, 10 сообщений, ждёт одобрения |
| `blocked` | Ничего |

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
| Изоляция кода | firejail | ✓ |
| Шифрование | Fernet (memory/), GPG (.env на Drive) | ✓ |
| Память | JSON + структурированное резюме + ChromaDB (семантика) | ✓ |
| Google Drive | rclone: триггерная sync файлов + cron бэкап | ✓ |
| Логи | TimedRotatingFileHandler + Drive cron | ✓ |
| Деплой | systemd + GitHub Actions CI/CD | ✓ |

---

## Дорожная карта

```
[✓] v0.1–0.9  — Фундамент, Agent, Конклав, Excel, Telegram Bot
[✓] v1.0      — VPS, CI/CD, шифрование, самосознание, vision, деплой
[✓] v1.1      — Веб-интерфейс, управление пользователями, долгая память, Drive sync
[✓] v1.2      — Живой голос в Конклаве, переработанная персона, git_log, UX-полировка
[✓] v1.3      — Семантическая память (ChromaDB), disaster recovery, отдельные reflections
[ ] v1.4      — Google Drive OAuth (личные аккаунты пользователей)
[ ] v1.x      — Тесты
```

---

## Лицензия

MIT. Используй, форкай, ломай и собирай обратно.

---

<div align="center">

*Агент, который помогает думать, а не заменяет мышление.*

</div>
