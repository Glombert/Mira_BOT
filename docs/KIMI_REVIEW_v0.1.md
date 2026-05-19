# Брифинг v0.2 для KimiCode — ревью клиента и план правок

**Контекст.** Ты сдал MVP веб-клиента (`~/mira-clients-dev/mira-clients`, версия 0.1) против контракта в `mira_agent/docs/API.md`, `docs/design.md`, `docs/KIMI_BRIEF.md`. Ревью проведено по коду клиента и `mira_agent/web/app.py`. Ниже — что нужно поправить и почему. Файлы и строки — точные.

---

## 1. Критические баги (без них v0.1 не взлетит даже в продакшене)

### 1.1 Telegram Login Widget не вызовет колбэк
**Файл:** `apps/web/components/auth/telegram-login.tsx:28-65`

Сейчас задано `data-auth-url=''` и нет `data-onauth`. Виджет ни редиректить, ни колбэк дёргать не будет. Глобальный `window.onTelegramAuth` объявлен, но виджет о нём не знает.

**Что сделать:**
```js
script.setAttribute('data-onauth', 'onTelegramAuth(user)');
```
И **передавать `user` целиком**, без выборочных полей. Telegram отдаёт ещё `photo_url` (и может ещё что-то в будущем), а сервер строит HMAC по **всем** ключам кроме `hash` — `mira_agent/web/app.py:130-140`. Если выкинуть `photo_url`, подпись не сойдётся и `_verify_telegram` вернёт `false`.

```js
window.onTelegramAuth = (user) => onAuth({ ...user, id: String(user.id) });
```

### 1.2 Кнопка "Пропустить авторизацию (dev)" видна всегда
**Файл:** `apps/web/components/auth/telegram-login.tsx:89-101`

В non-mock сборке нажатие шлёт `{hash: 'mockhash'}` → бэкенд вернёт `{ok: false, error: 'Ошибка авторизации'}`. Пользователь подумает что всё сломано.

**Что сделать:** пропускать `mockEnabled: boolean` пропом сверху (читать `NEXT_PUBLIC_MIRA_MOCK` в `chat-page.tsx`), рендерить кнопку только когда `true`.

### 1.3 Утечка WS-слушателей при повторной авторизации
**Файл:** `apps/web/components/chat/chat-page.tsx:61-105`

`connectClient` регистрирует пять `c.on(...)` и не отписывается. После сценария `auth_required → showAuth → новый логин → connectClient(client)` каждый ивент `message`/`ready`/… срабатывает дважды, потом трижды.

**Что сделать:** хранить unsubscribe-функции (которые возвращает `c.on`) в ref, вызывать все перед повторной регистрацией.

---

## 2. Бэкенд требует доработки — без них клиент не сможет работать локально/в полную силу

Это нужно добавить **в `mira_agent/web/app.py`** (бэкенд). Координируй с владельцем (Andrey).

### 2.1 CORS middleware (за env-флагом)
**Файл:** `mira_agent/web/app.py`, после `app = FastAPI(...)` на строке 90.

Сейчас CORS-мидлвари нет. С `localhost:3000 → localhost:8000` любой `fetch('/auth/telegram')` упадёт в браузере. WebSocket пройдёт (там other-origin policy), `fetch` — нет. Без этого dev-режим работает только в mock.

```python
if os.getenv("MIRA_ALLOW_LOCAL_CORS") == "1":
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
```

### 2.2 `GET /history?session=...&limit=50`
**Файл:** `mira_agent/web/app.py`, рядом с `/health` (строка 281).

Сервер уже хранит сессию в `mira.db` через `_load_session(user_id)` (строки 172-184). После reload страницы клиент стартует с пустого чата — но Мира **помнит** прошлые сообщения. Пользователь видит чистый экран, пишет "Что я спрашивал?", получает осмысленный ответ — диссонанс.

```python
@app.get("/history")
async def history(session: str = "", limit: int = 50):
    tg_id = _verify_session(session) if session else None
    if not tg_id:
        raise HTTPException(status_code=401, detail="Unauthorized")
    user_id = _web_user_id(tg_id)
    msgs = _load_session(user_id)
    # Отдать только user/assistant, без system, последние N
    visible = [m for m in msgs if m.get("role") in ("user", "assistant")][-limit:]
    return {"messages": visible}
```

### 2.3 `TELEGRAM_BOT_USERNAME` в `.env`
Сейчас в `mira_agent/.env` его нет (есть только `TELEGRAM_BOT_TOKEN`, `OWNER_TELEGRAM_ID`). При невалидной сессии сервер шлёт `{"type":"auth_required","bot":""}` — клиент не сможет показать виджет. Узнай у владельца username бота (`@…` из BotFather, без `@`) и пропиши:
```
TELEGRAM_BOT_USERNAME=…
```
Этот же username — в `NEXT_PUBLIC_BOT_USERNAME` клиента.

---

## 3. Клиентские доработки (вторая итерация)

### 3.1 Загрузка истории при подключении
После реализации `GET /history` (см. 2.2) в `chat-page.tsx` после `c.on('ready', ...)` сделай вызов `client.fetchHistory()`, отрендери в state до показа `setShowAuth(false)`. Добавь метод `fetchHistory()` в `packages/shared/src/api/mira-client.ts` рядом с `health()`.

### 3.2 `whoami` — модалка вместо системного сообщения в чате
**Файл:** `apps/web/components/chat/chat-page.tsx:147-150` + новая модалка.

`docs/KIMI_BRIEF.md:180` явно требует "модалка с инфо о профиле". Сейчас `whoami` приходит как `system`-сообщение и теряется в потоке.

**Что сделать:** при нажатии на иконку профиля — открыть модалку (компонент `<WhoamiModal />`), внутри модалки вызвать `sendCommand('whoami')`, ответ из `c.on('system', …)` парсить если ожидается whoami-ответ (можно завести флаг `pendingWhoami`). Альтернатива чище — `await`-обёртка в клиенте: `client.whoami(): Promise<WhoamiInfo>`.

### 3.3 Обработать `gdrive_auth_url` и `files`
**Файл:** `apps/web/components/chat/chat-page.tsx`

Эти типы есть в `ServerMessage` (`packages/shared/src/types/index.ts:38-39`), но в UI не обрабатываются. Минимум — fallback на `system`-сообщение с кликабельной ссылкой для `gdrive_auth_url`. Полноценная поддержка — в v0.3.

### 3.4 Дизайн: убрать `backdrop-blur-sm` из header
**Файл:** `apps/web/components/chat/chat-header.tsx:17`

`docs/design.md:253` явно запрещает glassmorphism. Заменить `bg-bg-base/80 backdrop-blur-sm` на сплошной `bg-bg-base`.

### 3.5 Мелочи кодстайла
- `apps/web/components/chat/chat-page.tsx:10` — неиспользуемый импорт `cn`, удалить.
- `packages/shared/src/api/mira-client.ts:243-244` — слушатель `'*'` недостижим через типизированный API. Либо добавить overload `on('*', handler: (msg: ServerMessage) => void)`, либо убрать.
- `MiraClient.fetchHistory` сделай с теми же мок-фикстурами для офлайн-разработки.

---

## 4. Ответы на твои `QUESTIONS.md`

1. **Dev-заглушка** — концептуально ок, но строго условный рендер только в mock-режиме (см. 1.2). Иначе сбивает с толку.
2. **CORS** — добавить на бэкенде с env-гейтом, см. 2.1. Mock не должен быть единственным dev-путём.
3. **`GET /history`** — приоритет высокий. Реализация в 10 строк, см. 2.2.
4. **`whoami` — модалка** — да, делай модалку, см. 3.2. Соответствует брифу и направлению дизайна.
5. **`TELEGRAM_BOT_USERNAME`** — спроси у владельца, добавь в `.env` и в `NEXT_PUBLIC_BOT_USERNAME`, см. 2.3.

---

## 5. Что НЕ надо трогать

- Контракт WS-сообщений совпадает 1-в-1 с `docs/API.md` — не переименовывай типы.
- `output: 'export'` Next.js — оставь как есть, оно для статической раздачи через nginx.
- Палитра, размеры, скругления — точно по `docs/design.md`, не отходи.
- Не добавляй файловый UI, drag-and-drop, Google-команды, напоминания — это v0.2+ после фикса критики выше.

---

## 6. Порядок работ

1. Сначала бэкенд (CORS + history + `BOT_USERNAME` в env) — это разблокирует нормальную dev-итерацию без mock.
2. Потом клиент: 1.1, 1.2, 1.3 — обязательны.
3. Потом: 3.1 (history UI), 3.2 (whoami модалка), 3.4 (glassmorphism).
4. Мелочи (3.3, 3.5) — параллельно или в конце.

Скриншоты после фиксов обнови — особенно auth (там сейчас "Bot domain invalid" из-за `localhost`, после правильного `TELEGRAM_BOT_USERNAME` и регистрации домена в BotFather должен показываться нормальный виджет).
