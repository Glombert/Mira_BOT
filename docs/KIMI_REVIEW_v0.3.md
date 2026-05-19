# Брифинг v0.4 для KimiCode — ревью v0.3 и план следующей итерации

**Контекст.** v0.3 закрыл регрессии v0.2 (R1-R5) и принёс новый функционал v0.2-scope: upload + drag-and-drop, command palette (Cmd+K), модалки Reminders / Drive / Whoami, mobile bottom sheets. Сборка чистая, дизайн соответствует `docs/design.md`. Но появились 5 новых багов — фиксить до Tauri.

См. рядом `KIMI_REVIEW_v0.1.md`, `KIMI_REVIEW_v0.2.md`, базовый контракт `API.md` / `design.md` / `KIMI_BRIEF.md`.

---

## Часть A. Багфиксы v0.3.1

### B1. `forget` (и `clear`) в палитре — без подтверждения

**Файлы:** `apps/web/lib/commands.ts:32,35`, `apps/web/components/palette/command-palette.tsx:36-50`.

`forget` (бэкенд: `mira_agent/web/app.py:514-522`) удаляет профиль + историю + semantic memory. Необратимо. В Cmd+K кликается одним нажатием.

**Чинить.** Добавить флаг `destructive?: boolean` в `CommandDef`. Для destructive команд в `handleSelect` — перед `onRun(cmd.cmd)` показывать confirm-dialog (отдельный компонент `<ConfirmDialog />` или нативный `window.confirm` для MVP). Для `forget` — обязательно. Для `clear` — желательно.

```ts
// в commands.ts
{ id: 'forget', ..., destructive: true },
{ id: 'clear', ..., destructive: true },

// в command-palette.tsx
if (cmd.destructive && !window.confirm(`Точно «${cmd.label}»? Действие необратимо.`)) return;
```

### B2. `whoami` через Cmd+K не открывает модалку

**Файл:** `apps/web/components/chat/chat-page.tsx:207-211,217-223`.

Иконка профиля → `handleWhoami` ставит `pendingWhoamiRef.current=true` → ответ перехватывается в модалку. Cmd+K → `whoami` → `handlePaletteRun` шлёт без флага → ответ падает в чат как system. Одна команда — две UX-реакции.

**Чинить.** Завести единую функцию `runCommand(cmd: string)`, которая для `whoami` (и в будущем других модальных команд) ставит соответствующий pending-флаг перед отправкой. Все вызовы (`handleWhoami`, `handlePaletteRun`, `RemindersModal`, `DriveModal`) переключить на неё.

### B3. Reminders / Drive модалки закрываются мгновенно, ответ улетает в чат

**Файлы:** `apps/web/components/ui/reminders-modal.tsx:79-81`, `apps/web/components/ui/drive-modal.tsx:38-58`.

Открыл «Напоминания» → жмёшь «Показать список» → `onClose()` → текст списка появляется внизу чата, а не в модалке. То же с «Привязать Drive» — `gdrive_auth_url` рендерится ссылкой в чате. Юзер ушёл в специализированный режим, ответ оказался в общем потоке.

**Чинить.** Не закрывать модалку по `onCommand`. Внутри модалки локально слушать соответствующий тип ответа с pending-флагом (как в R1 fix для whoami). Удобнее — ввести универсальный механизм в `MiraClient`:

```ts
// packages/shared/src/api/mira-client.ts
sendCommandAwait<T extends ServerMessage['type']>(
  cmd: string,
  expectedTypes: T[],
  timeoutMs = 10000
): Promise<Extract<ServerMessage, { type: T }>>
```

Внутри: подписка на ожидаемые типы, отписка после первого ответа или таймаута, возврат результата. Тогда модалки делают `await client.sendCommandAwait('reminders', ['system'])` и рендерят результат внутри себя — список напоминаний в той же модалке, без перехода в чат.

После этого:
- RemindersModal: «Показать список» → внутри модалки появляется список + кнопки ❌ напротив каждого reminder (парсить текст ответа `web/app.py:686-693`).
- DriveModal: «Привязать Drive» → ждать `gdrive_auth_url`, открыть в новой вкладке + показать инфо в модалке. «Список файлов» → ждать `system` с распарсенным списком.

Если структурированно парсить ответы лень — минимум: показывать сырой текст ответа внутри модалки и не закрывать её.

### B4. Drag-leave flicker

**Файл:** `apps/web/components/chat/chat-page.tsx:275-278`.

При перемещении курсора над дочерними элементами `dragLeave` фиксирует уход — overlay мигает.

**Чинить.** Счётчик enter/leave:

```ts
const dragCounterRef = useRef(0);
const handleDragEnter = (e: React.DragEvent) => {
  e.preventDefault();
  dragCounterRef.current++;
  setIsDragging(true);
};
const handleDragLeave = (e: React.DragEvent) => {
  e.preventDefault();
  dragCounterRef.current--;
  if (dragCounterRef.current === 0) setIsDragging(false);
};
const handleDrop = (e: React.DragEvent) => {
  e.preventDefault();
  dragCounterRef.current = 0;
  setIsDragging(false);
  // ...
};
```

И добавить `onDragEnter={handleDragEnter}` к контейнеру.

### B5. `isThinking` state не используется

**Файл:** `apps/web/components/chat/chat-page.tsx:35,118-119,148,153`.

`useState(false)` + `setIsThinking(true/false)` вызовы есть, но компонент state нигде не читает (thinking-bubble добавляется в `messages` отдельно). Мёртвый код — удалить state и все вызовы `setIsThinking`.

---

## Часть B. Мелкая чистка

- `chat-page.tsx:19-23` — `formatBytes` дублирует `formatSize` из `chat-message.tsx:143-147`. Вынести один `formatSize` в `apps/web/lib/utils.ts`, импортить из двух мест.
- После реализации B3 (`sendCommandAwait`) проп `onCommand` в Reminders/Drive модалках уходит — там будет прямой доступ к `client` через проп либо контекст.
- В палитре после `sendCommandAwait` команды с aргументами тоже можно ждать ответ и показывать его inline. Но пока — закрываем палитру как сейчас.

---

## Часть C. Проверить вручную (не баг, но рискованно)

- `datetime-local` отдаёт `"2026-05-17T15:30"` без секунд. Сервер: `web/app.py:670-672` → `tools/scheduler.schedule_reminder(user_id, trigger_at, message)`. Нужно убедиться, что `schedule_reminder` парсит формат без секунд (вероятно через `datetime.fromisoformat()` — съест). Проверь руками или добавь секунды на клиенте: `${datetime}:00`.
- Палитра Cmd+K в браузере иногда перехватывается dev-tools. Это норма, не баг.

---

## Часть D. План v0.4 — Tauri desktop shell

После v0.3.1 фиксов веб-клиент функционально полный для MVP. Следующий шаг — упакованный desktop-клиент.

### D1. Структура

Новый workspace `apps/desktop/` в существующей monorepo. Использует тот же `@mira/shared` пакет (типы + `MiraClient`). UI — реюз React-компонентов из `apps/web/components/` через символическую ссылку или прямой импорт через путь алиаса в `tsconfig.json`. Лучший вариант — вынести компоненты в отдельный пакет `packages/ui/`, чтобы и web, и desktop их шарили. Если это раздувает scope — оставь как есть и копируй (потом отрефакторим).

```
apps/
  desktop/
    src-tauri/        # Rust backend
      Cargo.toml
      src/main.rs
      tauri.conf.json
    src/              # React frontend (по сути копия apps/web)
      App.tsx
      main.tsx
    index.html
    package.json
    vite.config.ts    # Tauri использует Vite, не Next.js
```

Установка: `cargo install tauri-cli@^2` + `npm install -D @tauri-apps/cli @tauri-apps/api`.

### D2. Минимальный MVP

1. **Окно с WebView** загружает React-приложение, по сути то же что `apps/web` без SSR.
2. **Нативный keyring для session token** — `tauri-plugin-stronghold` или системный keyring (`keyring-rs`). См. `docs/API.md:38-40` — там это явно указано как требование.

   Реализация: в `MiraClient` инжектится `SessionStorage` интерфейс:
   ```ts
   interface SessionStorage {
     get(): Promise<string | null>;
     set(token: string): Promise<void>;
     clear(): Promise<void>;
   }
   ```
   Web реализация: `localStorage` (как сейчас). Desktop: Tauri invoke в Rust → keyring.

3. **Системный трей** — иконка-звезда, контекстное меню «Открыть Миру / Скрыть / Выход». При закрытии окна — минимизация в трей, не выход.

4. **Auto-launch при старте** (опционально, через настройку) — `tauri-plugin-autostart`.

### D3. Особенности Telegram Auth на desktop

Telegram Login Widget работает только в браузере. Для desktop:
- Открыть `https://oauth.telegram.org/auth?bot_id=...&origin=...&return_to=tauri-deep-link` в системном браузере (`@tauri-apps/api/shell`).
- Зарегистрировать deep-link обработчик (`tauri-plugin-deep-link`) на схему `mira://auth?id=...&hash=...`.
- В обработчике вызвать `client.authenticate(...)` как сейчас.

Это требует регистрации `mira://` схемы в `tauri.conf.json` + согласования return_to URL с владельцем бота (Andrey).

Альтернатива (проще на старте): встроить Telegram Login Widget в WebView через iframe или прямой HTML — но Telegram блокирует виджет на не-зарегистрированных доменах. Так что deep-link единственный честный путь. Сначала запусти веб-сборку в WebView и оставь auth на потом — потестируйте mock-режимом.

### D4. Что НЕ делать в v0.4

- React Native mobile — v0.5+.
- Streaming ответов LLM — требует изменения `providers.py` бэкенда.
- Push-уведомления — отдельная инфраструктура (FCM/APNS).
- Голосовой ввод.
- Light theme.
- Свои настройки (отдельный экран) — пока всё через `whoami` модалку.

### D5. Порядок работ для v0.4

1. **Сначала v0.3.1** (B1-B5 + чистка из части B) — полдня.
2. **packages/ui выделение** (опционально, если хочется чисто) — день.
3. **Tauri-скелет** — окно, билд, runs.
4. **Mock-режим внутри Tauri** — провер UX в WebView, скриншоты.
5. **SessionStorage абстракция + keyring-реализация** в desktop.
6. **Deep-link + Telegram auth** — после согласования с владельцем.
7. **Системный трей**.

Скриншоты desktop-окна (Linux/macOS/Windows если есть возможность) положить в `apps/desktop/screenshots/`.

---

## Часть E. Бэкенд-блокеры (статус неизменный)

Не сделано на бэкенде `mira_agent/web/app.py` — KimiCode не трогает:
- `CORSMiddleware` за env-флагом `MIRA_ALLOW_LOCAL_CORS=1`.
- `GET /history?session=...&limit=50`.
- `TELEGRAM_BOT_USERNAME` в `.env`.

Без этого:
- `fetchHistory` всегда падает в catch (клиент это переживает корректно — пустой чат вместо истории).
- Telegram Login Widget не отрисуется без username.
- CORS блокирует `/auth/telegram` `fetch` при dev `localhost:3000 → :8000` (WebSocket работает, HTTP — нет).

Эти три правки делает владелец. Клиент к ним готов.

---

## Часть F. Когда сдавать

После v0.3.1: пересобрать `mira-clients-v0.X.zip`, обновить скриншоты (если изменился UI — например, confirm-dialog для destructive команд), новый `QUESTIONS.md` если возникли вопросы.

После v0.4 Tauri: первый билд для Linux (`.AppImage` или `.deb`), скриншоты окна.
