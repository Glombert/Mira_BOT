# Брифинг v0.3 для KimiCode — ревью v0.2 и план следующей итерации

**Контекст.** v0.2 закрыл всю критику из `KIMI_REVIEW_v0.1.md` (см. рядом). Сборка чистая, контракт WS-сообщений соответствует `docs/API.md`. Но появились **три регрессии** + косметика — починить в первую очередь. Потом — функционал v0.2 (uploads, команды, Google, reminders, command palette).

---

## Часть A. Регрессии v0.2 — чинить срочно

### R1. Whoami отображается дважды (чат + модалка)
**Файл:** `apps/web/components/chat/chat-page.tsx:109-112` и `189-197`

Общий обработчик `c.on('system', …)` в `connectClient` пушит whoami как system-сообщение в чат. Отдельный `useEffect` ниже регистрирует ещё одного слушателя `'system'`, который открывает модалку. Оба срабатывают.

**Чинить.** Завести ref-флаг `pendingWhoamiRef: useRef(false)`. В `handleWhoami` ставить `true` перед `sendCommand('whoami')`. В **едином** system-обработчике (один на весь компонент, убрать дубль из второго useEffect):
```ts
const unsubSystem = c.on('system', (msg) => {
  setIsThinking(false);
  if (pendingWhoamiRef.current) {
    setWhoamiContent(msg.content);
    pendingWhoamiRef.current = false;
    return;  // в чат не добавлять
  }
  addMessage({ id: generateId(), type: 'system', content: msg.content, timestamp: Date.now() });
});
```

Это также решает R2 — никаких эвристик `startsWith('Имя:')` больше не нужно.

### R2. Эвристика whoami `startsWith('Имя:')` ломкая
Решается через R1. После фикса — удалить хрупкую проверку на строке `chat-page.tsx:192`.

### R3. Реконнект перетирает локальные сообщения
**Файл:** `apps/web/components/chat/chat-page.tsx:71-89`

`fetchHistory` вызывается в каждом `c.on('ready', …)`. При WS-реконнекте сервер шлёт `ready` снова — клиент перезагружает историю и делает `setMessages(historyMsgs)`, стирая то, что юзер видел в текущей сессии (включая последние реплики и `thinking`).

**Чинить.** Завести `historyLoadedRef = useRef(false)`. В ready-обработчике:
```ts
if (!historyLoadedRef.current) {
  historyLoadedRef.current = true;
  c.fetchHistory(50).then(...).catch(...);
}
```
Сбрасывать `historyLoadedRef.current = false` только при `auth_required` (т.е. при смене пользователя).

### R4. Косметика
- `apps/web/components/chat/chat-message.tsx:7` — `import { cn } from '@/lib/utils'` без использования. Удалить.
- `apps/web/components/auth/telegram-login.tsx:69` — `delete window.onTelegramAuth` в TS strict может ругаться (зависит от tsconfig). Если ругается — `window.onTelegramAuth = undefined`.

### R5. Скриншоты
`02-chat-empty-desktop.png` и `04-chat-with-messages.png` сейчас идентичны (оба — пустой чат "Не в сети", поле "Подключение…"). Скриншот-скрипт явно гонялся без mock.

**Чинить.** Запустить `apps/web/scripts/screenshot.js` с `NEXT_PUBLIC_MIRA_MOCK=true` чтобы:
- 02 показал статус "В сети", имя "Andrey", пустой чат с подсказкой.
- 04 показал реальную переписку (mock сам отдаст `ws_message_simple` / `ws_message_markdown`).

---

## Часть B. Что блокировано бэкендом (не делать пока не появится)

Бэкенд (`mira_agent/web/app.py`) ещё **не** получил:
- `CORSMiddleware` за env-флагом `MIRA_ALLOW_LOCAL_CORS=1`
- `GET /history?session=…&limit=50`
- `TELEGRAM_BOT_USERNAME` в `.env`

Эти три правки координирует владелец. Клиент v0.2 уже к ним готов — `fetchHistory` падает в `catch` корректно, виджет ждёт username из env. **Не пиши Python**, не редактируй `mira_agent/`.

---

## Часть C. План v0.3 — функционал

Все эндпойнты и WS-команды для нижеперечисленного **уже работают** в `web/app.py`. Бэкендных доработок не требуется.

### C1. Загрузка файлов (`POST /upload`)

**Эндпойнт:** `web/app.py:377-410`. Лимит 20 МБ, rate-limit 20 файлов/мин. См. `docs/API.md` раздел 2 «POST /upload».

**UI:**
- **Paperclip-кнопка** слева в `ChatInput` (lucide-react: `Paperclip`).
- **Drag-and-drop** в зону чата: overlay поверх `containerRef` при `dragenter` — пунктирная рамка `--accent`, текст «Брось файл сюда».
- **Прогресс-бар** на сообщение-карточку (для файлов >1 МБ). Используй `XMLHttpRequest` (не `fetch`) для нативного progress event:
  ```ts
  const xhr = new XMLHttpRequest();
  xhr.upload.addEventListener('progress', (e) => { ... });
  xhr.open('POST', `${baseUrl}/upload?session=${session}`);
  xhr.send(formData);
  ```
- **Обработка ошибок:**
  - `401` — `client.disconnect()`, показать auth.
  - `413` — system-сообщение от Миры (текст придёт в `detail`).
  - `429` — то же, плюс отсчёт `Retry-After`.
- **Успех:** локальное сообщение «Загружено: filename» как `system`, плюс серверный отвечает обычным WS-сообщением при необходимости.

**Метод в MiraClient:** `uploadFile(file: File, onProgress?: (pct: number) => void): Promise<UploadResult>`. Мок — резолвится через 1.5с с фиктивным `{ok: true, filename, size}`.

### C2. Список файлов (`command: files`)

**Эндпойнт:** WS `{"type":"command","cmd":"files"}` → сервер шлёт `{"type":"files", "files":[...]}`. Уже частично есть UI в `chat-message.tsx:107-122` (рендер карточки).

**Доработка:**
- Сделать имена кликабельными: ссылка на `${baseUrl}/files/{dir}/{name}?session=${session}`. Добавить хелпер `client.fileUrl(dir, name)` в `mira-client.ts`.
- Кнопка-папка в шапке или элемент в command palette → `sendCommand('files')`.
- Mock-фикстура для `files` уже есть форматом — добавь `ws_files_demo` если нужно.

### C3. Command Palette (Cmd+K / Ctrl+K)

**Контекст:** `docs/design.md:199-205` явно требует палитру команд в стиле Linear/Cmd+K. Список команд — `docs/API.md:153-170`.

**UI:**
- Глобальный keybind `Cmd+K` (Mac) / `Ctrl+K` (остальные).
- Кнопка-меню (lucide: `Command`) в шапке между профилем и trash.
- Модалка по центру (max-w-lg), поиск по `name + description`, список с иконкой + названием + кратким описанием.
- Для команд **без аргументов** (`clear`, `whoami`, `files`, `forget`, `gdrive_status`, `gdrive_login`, `reminders`) — клик сразу шлёт `sendCommand(...)`.
- Для команд **с аргументами** — раскрывается мини-форма:
  - `remind <ISO> <text>` — date-picker (input type=datetime-local) + textarea + кнопка «Создать».
  - `remind_cancel <id>` — список активных reminders с кнопкой ❌ (вызывает `reminders` сначала, кеширует).
  - `gdrive_list [folder]` — поле «папка» опциональное.
  - `gdrive_get <id>` — поле id.
  - `gcal [N]` — поле количество (default 10).
  - `gcal_create <текст>` — textarea с примером «Встреча с Колей завтра в 15:00».
  - `gsheet <id> [range]` — два поля.
  - `gsheet_create [title]` — поле title.

**Структура кода:** новый компонент `apps/web/components/palette/command-palette.tsx` + список команд из конфига `apps/web/lib/commands.ts`. Скрытие команд по статусу пользователя — пока не делай, статус не приходит в WS. Если зовёт guest — сервер сам ответит `system: Требуется одобрение.`.

### C4. Reminders — отдельная модалка

**Бриф:** `docs/KIMI_BRIEF.md:197-198`.

В Cmd+K палитре уже будет точка входа, но для reminders отдельный экран удобнее:
- Кнопка-колокольчик (lucide: `Bell`) рядом с профилем в шапке.
- Модалка со списком (`sendCommand('reminders')` при открытии).
- Внизу — форма создания (date-picker + текст + кнопка).
- Каждый reminder — строка с временем, текстом, кнопкой ❌.

### C5. Google Drive — отдельная модалка

- Иконка `Cloud` в шапке (рядом с колокольчиком).
- Модалка:
  - Если не привязан → кнопка «Привязать Google Drive» (шлёт `gdrive_login`, сервер вернёт `gdrive_auth_url` — открыть в новом окне).
  - Если привязан → email + список файлов (по `gdrive_list`), клик по файлу → `gdrive_get <id>` → success-toast «Файл скачан в output/».

### C6. Mobile-адаптация модалок

`docs/design.md:231` говорит: «Bottom sheet вместо модалок на телефоне». На viewport <640px все модалки (whoami, command palette, reminders, drive) должны быть bottom sheet — выезжать снизу, занимать 70-90% высоты, swipe-down для закрытия (минимум — drag handle сверху).

---

## Часть D. Чего НЕ делать в v0.3

- Не делать streaming ответа Миры (требует изменения `providers.py` на бэкенде).
- Не делать push-уведомления.
- Не делать light theme.
- Не делать Tauri/RN — это v0.4+.
- Не трогать контракт `ServerMessage` / `ClientMessage` без согласования.
- Не пытаться скрывать команды по статусу — статус в WS не приходит, сервер сам откажет.

---

## Часть E. Порядок и проверка

1. Сначала **v0.2.1**: R1, R2, R3, R4, R5 (полдня). Пересобрать архив, обновить скриншоты с mock.
2. Потом **v0.3.0**:
   - C1 (upload + drag-and-drop) — 1 итерация.
   - C3 (command palette) — 1 итерация, это самое крупное.
   - C2 (files clickable) — 0.5 итерации, можно вместе с C1.
   - C4, C5 (reminders, drive модалки) — 1 итерация.
   - C6 (mobile bottom sheets) — 0.5 итерации в конце.
3. Каждую итерацию — `next build` без ошибок, ручная проверка в mock, скриншоты.

**QUESTIONS-файл** обновлять как обычно: если по ходу вылезут вопросы — складывай туда и присылай вместе с архивом.
