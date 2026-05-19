# Mira API — контракт для клиентских приложений

Документ для разработчиков клиентов (web SPA, desktop Tauri, Android).
Описывает что отдаёт `web/app.py` на VPS — единственный backend для всех клиентов.

**База:** `https://mira-bot.duckdns.org` (продакшен) или `http://localhost:8000` (локально).
**Протоколы:** HTTPS + WSS. Никаких прямых обращений к Telegram API или к БД.

---

## 1. Аутентификация — Telegram Login Widget

Mira не имеет собственного логина. Доверяет Telegram.

### Flow

1. **Клиент показывает кнопку "Войти через Telegram".**
   - Web: встраивает скрипт `https://telegram.org/js/telegram-widget.js?22` с `data-telegram-login=$BOT_USERNAME` и `data-auth-url=$REDIRECT`.
   - Native: открывает `https://oauth.telegram.org/auth?bot_id=...&origin=...&return_to=...` в системном браузере и слушает deep link callback.

2. **Telegram отдаёт клиенту данные о пользователе** в query-params:
   ```
   id=12345&first_name=Andrey&last_name=&username=glombert&auth_date=1715692800&hash=abc...
   ```

3. **Клиент шлёт эти параметры на сервер:**
   ```
   GET /auth/telegram?id=12345&first_name=Andrey&auth_date=...&hash=...
   ```

4. **Сервер проверяет HMAC-подпись** (от `BOT_TOKEN`, по протоколу Telegram Login Widget) и отвечает:
   ```json
   { "ok": true, "session": "12345:Andrey:1715692800:abc...", "name": "Andrey", "is_new": false }
   ```
   Ошибка: `{ "ok": false, "error": "Ошибка авторизации" }`.

5. **Клиент сохраняет `session` в защищённое хранилище:**
   - Web: `localStorage` (приемлемо для приватного сервиса до 100 пользователей)
   - Desktop (Tauri): keyring через `tauri-plugin-stronghold` или `keyring-rs`
   - Android: `EncryptedSharedPreferences` (Jetpack Security)

   **Никогда** не логировать токен, не отправлять в analytics, не класть в plain-text файл.

### Формат session token

```
{tg_id}:{name}:{issued_at_unix}:{hmac_hex_32}
```
- `hmac_hex_32` = первые 32 hex-символа `HMAC-SHA256(bot_token, "{tg_id}:{name}:{issued_at_unix}")`.
- Срок жизни: **30 дней** с момента `issued_at`.
- Подпись считается на сервере; клиент токен не декодирует, обращается с ним как с opaque-строкой.

### Использование токена

Все защищённые эндпойнты принимают токен в **query-параметре `session=...`** (не в заголовке).

```
POST /upload?session={token}
GET  /files/inbox/foo.txt?session={token}
WS   /ws?session={token}
```

Если токен невалидный или истёк:
- HTTP: `401 Unauthorized`
- WebSocket: сначала придёт `{"type": "auth_required", "bot": "<BOT_USERNAME>"}`, потом сервер закроет соединение с кодом `4001`.

---

## 2. HTTP эндпойнты

### `GET /health` — liveness

Не требует авторизации. Используется для status-индикатора в UI.

```json
{
  "status": "ok",
  "bot_alive": true,
  "web_alive": true
}
```

`bot_alive` / `web_alive` — true если соответствующий процесс писал heartbeat за последние 120 секунд.

### `GET /auth/telegram` — обмен Telegram-данных на session

Описан выше. Возвращает JSON с `session`.

### `POST /upload` — загрузка файла в inbox пользователя

- **Auth:** session-token в query.
- **Body:** `multipart/form-data`, поле `file`.
- **Ограничения:** 20 МБ, 20 файлов / минуту.

**Успех (200):**
```json
{ "ok": true, "filename": "report.xlsx", "size": 12345 }
```

**Ошибки:**
- `401` — нет/невалидный session
- `400` — недопустимое имя файла (path traversal, пустое)
- `413` — больше 20 МБ. `detail` — текст от Миры на русском: «Файл слишком тяжёлый — я могу принимать до 20 МБ...»
- `429` — превышен rate limit. Заголовок `Retry-After: <секунды>`, `detail` — текст от Миры.

Имя файла нормализуется на сервере (basename + удаление `\x00`). Клиент может слать оригинальное имя как есть, но без слешей.

### `GET /files/{inbox|output}/{filename}` — скачивание

- **Auth:** session в query.
- **Префиксы:** только `inbox/` (загруженные пользователем) или `output/` (созданные Мирой).

**Успех:** `application/octet-stream` + `Content-Disposition: attachment; filename=...`

**Ошибки:**
- `401` — нет session
- `403` — путь вне `inbox/` или `output/` (попытка обойти sandbox)
- `404` — файла нет

---

## 3. WebSocket `/ws` — диалог в реальном времени

Главный канал. Через него идёт переписка, команды, статус-ответы.

### Подключение

```
ws(s)://host/ws?session={token}
```

Если токен принимается — сервер шлёт:
```json
{ "type": "ready", "name": "Andrey" }
```

Если нет — `{"type": "auth_required", "bot": "<BOT_USERNAME>"}` и close `4001`.

### Сообщения от клиента → серверу

Все — JSON со строковым полем `type`.

| `type` | Поля | Что делает |
|---|---|---|
| `ping` | — | Liveness-проверка. Сервер отвечает `pong`. Рекомендую слать каждые 30 секунд. |
| `command` | `cmd: string` | Структурированная команда (см. ниже). |
| (любой другой / без type) | `content: string` | Обычное сообщение от пользователя. Идёт в LLM. |

### Команды (`type: "command"`)

`cmd` — строка вида `<keyword>` или `<keyword> <args>`.

| `cmd` | Что делает | Доступ |
|---|---|---|
| `clear` | Очистить историю диалога | все |
| `whoami` | Профиль пользователя | все |
| `files` | Список файлов в inbox/output | все |
| `forget` | Сбросить профиль + историю + векторную память | все |
| `gdrive_login` | Получить URL для OAuth Google Drive | regular/owner |
| `gdrive_status` | Статус привязки Drive | regular/owner |
| `gdrive_list [folder]` | Список файлов на Drive | regular/owner |
| `gdrive_get <file_id>` | Скачать с Drive в `output/` | regular/owner |
| `gcal [N]` | Ближайшие N событий из Calendar | regular/owner |
| `gcal_create <текст>` | Создать событие из фразы | regular/owner |
| `gsheet <id> [range]` | Прочитать Google Таблицу | regular/owner |
| `gsheet_create [title]` | Создать новую Таблицу | regular/owner |
| `remind <ISO-дата> <текст>` | Создать напоминание | regular/owner |
| `reminders` | Список активных напоминаний | regular/owner |
| `remind_cancel <id>` | Отменить напоминание | regular/owner |

Команды для **guest** возвращают `{"type": "system", "content": "Требуется одобрение."}`.

### Сообщения от сервера → клиенту

| `type` | Поля | Когда приходит |
|---|---|---|
| `ready` | `name` | После успешной аутентификации, первое сообщение |
| `auth_required` | `bot` | Невалидный session — клиент должен запустить Login Widget заново |
| `pong` | — | В ответ на `ping` |
| `thinking` | — | Сервер начал обработку текстового сообщения (показать индикатор) |
| `message` | `content` | Ответ Миры на пользовательский текст. Также используется для rate-limit-предупреждений (Мира говорит «помедленнее»). |
| `system` | `content` | Технические/служебные ответы: команды, лимиты гостя, статусные предупреждения. UI должен отрисовывать заметно иначе чем `message`. |
| `error` | `content` | Сбой LLM или обработки. Сессия не разорвана. |
| `files` | `files: [{name, dir, size}]` | Ответ на `command: files` |
| `gdrive_auth_url` | `url` | Ответ на `command: gdrive_login` — клиент должен открыть URL в браузере |

### Жизненный цикл сообщения

```
client → { "content": "Привет, Мира" }
server → { "type": "thinking" }
server → { "type": "message", "content": "Здравствуй..." }
```

При классификации как сложной задачи (`code`/`complex`/`search`) — Конклав запускается параллельно. Ответ всё равно один — `{"type": "message"}`. **Streaming сейчас не реализован**: клиент получает финальный текст разом.

### Лимиты на WS-канале

- 60 сообщений / минуту — превышение → `{"type": "message", "content": "Эй, помедленнее..."}`
- Гость (status=`guest`) — 10 сообщений всего, потом отказ
- Статус `blocked`/`rejected` — все сообщения отбиваются с `system`

---

## 4. Структура user_id

Telegram-боту и веб-клиенту нужно одинаковое представление, чтобы профиль был общий:

```
user_id = "tg_{tg_id}"
```

Этот ID *внутренний* — клиент его не использует напрямую. Запоминать его клиенту не нужно: сервер сам выводит из session token.

---

## 5. CORS и nginx

**Текущая конфигурация:** `web/app.py` не имеет CORS middleware. Если клиент отдаётся с того же домена что и API — всё работает. Если клиент будет на другом домене (например, отдельный CDN) — нужно добавить `fastapi.middleware.cors.CORSMiddleware` с whitelisted origins.

nginx уже проксирует `/` → 8000, `/ws` → 8000 с `Upgrade`-заголовком. Сертификат от Let's Encrypt через DuckDNS.

---

## 6. Что ещё надо знать клиенту

### Статусы пользователя

Возвращается в `whoami`:
- `owner` — владелец, все права
- `regular` — одобренный, полный доступ к команд и инструментам
- `guest` — 10 сообщений, потом ждёт одобрения; нет Google-команд, нет загрузки файлов
- `rejected` — отклонён
- `blocked` / `blacklisted` — чёрный список

UI должен **скрывать** недоступные кнопки в зависимости от статуса, а не показывать их с серым цветом — Мира уже сама вежливо откажет в `system`-сообщении, но лучше не давать тыкать.

### Что НЕ нужно делать на клиенте

- **Хранить переписку.** История — на сервере, в `mira.db`. Клиент получает её через WS (сейчас — только активная сессия; для истории за прошлые дни эндпойнт ещё не сделан, см. roadmap ниже).
- **Дублировать rate limit.** Сервер сам отбивает. Клиент только показывает сообщение Миры.
- **Шифровать токен.** На сервере уже HMAC. На клиенте важно не утечь — хранить в платформенных secrets, не в plain JSON.
- **Парсить markdown в `system` сообщениях.** Они — plain text. В `message` Мира может вернуть markdown — рендерить безопасным рендером (без HTML).
- **Создавать своих пользователей.** Источник правды — Telegram.

### Чего пока нет в API (но может понадобиться)

| Что | Зачем | Сложность |
|---|---|---|
| `GET /history?session=...&limit=50` | Подгрузить переписку при открытии клиента | низкая, добавляется в web/app.py |
| Streaming ответа LLM по WS | UX «печатает...» как у ChatGPT | средняя, нужны изменения в `providers.call` |
| Push-уведомления | Напоминания на мобильном | высокая (FCM для Android, нужны новые таблицы) |
| Голосовой ввод | Voice → text → LLM | внешняя, не на сервере |

Не добавляй эти эндпойнты в backend сам — обсуди с владельцем (Andrey) что приоритетно. Серверный код держится максимально простым.

---

## 7. Пример минимального клиента (web, vanilla JS)

```javascript
// 1. Авторизация
const session = localStorage.getItem("mira_session");
if (!session) {
  // показать Telegram Login Widget...
  // после колбэка:
  const params = new URLSearchParams(telegramData);
  const r = await fetch(`/auth/telegram?${params}`);
  const data = await r.json();
  if (data.ok) {
    localStorage.setItem("mira_session", data.session);
  }
}

// 2. Подключение к WS
const ws = new WebSocket(`wss://mira-bot.duckdns.org/ws?session=${session}`);

ws.onmessage = (e) => {
  const msg = JSON.parse(e.data);
  switch (msg.type) {
    case "ready":         hideLogin(); showName(msg.name); break;
    case "auth_required": localStorage.removeItem("mira_session"); showLogin(); break;
    case "thinking":      showSpinner(); break;
    case "message":       hideSpinner(); renderMira(msg.content); break;
    case "system":        renderSystem(msg.content); break;
    case "error":         renderError(msg.content); break;
    case "files":         renderFileList(msg.files); break;
    case "pong":          /* alive */ break;
  }
};

// 3. Отправка
function sendMessage(text) {
  ws.send(JSON.stringify({ content: text }));
}

function sendCommand(cmd) {
  ws.send(JSON.stringify({ type: "command", cmd }));
}

// 4. Keep-alive
setInterval(() => ws.send(JSON.stringify({ type: "ping" })), 30000);

// 5. Загрузка файла
async function uploadFile(file) {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`/upload?session=${session}`, { method: "POST", body: fd });
  if (r.status === 429) {
    const j = await r.json();
    renderSystem(j.detail);  // голос Миры про «помедленнее»
    return;
  }
  return r.json();
}
```
