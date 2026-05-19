# Брифинг v0.5 для KimiCode — ревью v0.4 и план следующей итерации

**Контекст.** v0.4 закрыл багфиксы v0.3.1 (B1-B5 + чистка) и заложил Tauri-скелет с окном и системным треем. Сборка веба чистая, Tauri-проект компилируется (системные deps нужны отдельно). Но при реализации B3 повторился тот же класс бага, что и в R1 — модальные ответы дублируются в чат. И Tauri-скелет загружает веб-бандл «как есть», без своей интеграции — окно есть, нативных возможностей нет.

См. рядом `KIMI_REVIEW_v0.1.md`, `KIMI_REVIEW_v0.2.md`, `KIMI_REVIEW_v0.3.md`, базовый контракт `API.md` / `design.md` / `KIMI_BRIEF.md`.

---

## Часть A. Багфикс v0.4.1

### B3R. Ответы модалок Reminders/Drive дублируются в чате

**Файлы:** `apps/web/components/chat/chat-page.tsx:120-130` (глобальные обработчики `c.on('system')` / `c.on('files')` / `c.on('gdrive_auth_url')`), `apps/web/components/ui/reminders-modal.tsx:36`, `apps/web/components/ui/drive-modal.tsx:38`.

Сценарий. Открыл «Напоминания» → жмёшь «Показать список». Внутри модалки `await client.sendCommandAwait('reminders', ['system'])`. Сервер отвечает `{type:'system', content:'…'}`. Срабатывают **оба** подписчика:

1. Модалкин (внутри `sendCommandAwait`) — рендерит результат в модалке (правильно).
2. Глобальный `c.on('system', …)` в `chat-page.tsx:120-130` — добавляет тот же текст в чат как system-сообщение (дубликат).

Это тот же класс что R1 (whoami), просто `pendingWhoamiRef` решил только частный случай whoami. Drive страдает зеркально — `gdrive_auth_url` появляется и в модалке (ссылкой), и в чате (через `chat-page.tsx:147-154`).

**Чинить.** Два варианта, выбери один:

**A. Уровень `chat-page` (грубо, но без изменения API):**
```ts
// в chat-page.tsx
const suppressRef = useRef<Map<ServerMessage['type'], number>>(new Map());

const suppressNext = (types: ServerMessage['type'][]) => {
  types.forEach((t) => suppressRef.current.set(t, (suppressRef.current.get(t) || 0) + 1));
};

// в глобальных обработчиках:
const unsubSystem = c.on('system', (msg) => {
  const n = suppressRef.current.get('system') || 0;
  if (n > 0) {
    suppressRef.current.set('system', n - 1);
    return;
  }
  // ... остальная логика
});
```
И передавать `suppressNext` в модалки как проп. Модалка вызывает `suppressNext(['system'])` **перед** `sendCommandAwait`.

**B. Уровень `MiraClient` (чище, но меняет семантику `on`):**

В `mira-client.ts` ввести приватную очередь awaiters. `sendCommandAwait` регистрирует «потребителя» с приоритетом — `_emit` отдаёт сообщение awaiter'у first-come-first-served, и **только если awaiter не нашёлся** — публичным слушателям. Это локально меняет поведение `on()`: для типов, на которые ждут модалки, публичные слушатели одно сообщение пропустят. Документировать в комментарии.

Рекомендую **B** — модалки и chat-page больше не связаны через ref-проп. Если боишься поломать что-то — делай **A**, грубее, но прозрачнее.

### SessionStorage абстракция полу-проводная

**Файлы:** `packages/shared/src/api/mira-client.ts:79,99-118`, `apps/web/components/chat/chat-page.tsx:52,150-153,108-111`.

`MiraClient` получил `setSession/loadSession/clearSession` (async, с `_sessionStorage`). Но `chat-page.tsx` всё ещё дёргает `localStorage` напрямую (строки 52 `localStorage.getItem`, 150 `localStorage.setItem`, 108-111 `localStorage.removeItem`), параллельно с `client.setSession(...)` без `await`.

Проблемы:
- `setSession` стал async — текущий код не ждёт промис. На вебе работает (нет инжектированного storage), но при подключённом keyring в desktop — race между localStorage и keyring.
- Внутри Tauri-WebView frontend всё равно использует localStorage. Keyring неактивен. Обещание `docs/API.md:38-40` про native secure storage не выполнено.

**Чинить:**

1. Создать `apps/web/lib/session-storage.ts`:
   ```ts
   import type { SessionStorage } from '@mira/shared';
   const KEY = 'mira_session';
   export const webSessionStorage: SessionStorage = {
     async get() { return typeof window !== 'undefined' ? localStorage.getItem(KEY) : null; },
     async set(token) { if (typeof window !== 'undefined') localStorage.setItem(KEY, token); },
     async clear() { if (typeof window !== 'undefined') localStorage.removeItem(KEY); },
   };
   ```
2. В `chat-page.tsx`:
   - Создать клиент с `sessionStorage: webSessionStorage`.
   - В useEffect: `const stored = await client.loadSession()` вместо чтения localStorage.
   - В handleAuth: `await client.setSession(result.session)` вместо setItem.
   - В `auth_required`: `await client.clearSession()` вместо removeItem.
3. Удалить прямые вызовы `localStorage.*` из `chat-page.tsx`.

После этого desktop сможет передать собственный `TauriSessionStorage` без изменений общего кода (см. T4 ниже).

---

## Часть B. Tauri — достройка до полноценного desktop (v0.5)

Сейчас `apps/desktop/` — это окно, которое загружает `apps/web/dist` как статический бандл. Окно и трей работают, но фронт **не знает что он в Tauri** — `window.__TAURI__` есть, но никто его не дёргает. Ниже — что нужно дополнить.

### T1. Tauri-aware frontend

**Решение (прагматичное):** conditional code внутри `apps/web`.

```ts
// apps/web/lib/runtime.ts
export const IS_TAURI = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
```

В `chat-page.tsx` (или там где создаётся `MiraClient`) выбирать storage:
```ts
import { webSessionStorage } from './session-storage';
import { IS_TAURI } from './runtime';

const storage = IS_TAURI
  ? (await import('./tauri-session-storage')).tauriSessionStorage
  : webSessionStorage;
```

Альтернатива — отдельный entry-point в `apps/desktop/src/`, переиспользующий компоненты через `packages/ui/` или path-alias. Чище, но требует выноса всех web-компонентов в shared пакет. Если хочется быстро — делай conditional. Если есть время на рефакторинг — выноси `packages/ui/`.

### T2. Иконка — звезда Миры, не дефолтная Tauri

`apps/desktop/src-tauri/icons/*` — дефолтные T-logo от `tauri init`. Сгенерируй из звезды (см. `apps/web/components/ui/star-avatar.tsx` — SVG-градиент `#FF8C42 → #FFB888`):

```bash
# из звезды 1024×1024 PNG:
npx @tauri-apps/cli icon path/to/star.png
```

Эта же иконка пойдёт в `system tray` (сейчас используется `app.default_window_icon()` — после замены автоматически подхватится).

### T3. Capabilities

`apps/desktop/src-tauri/capabilities/default.json` сейчас содержит только `core:default`. После добавления плагинов (T4, T5) — обновить:
```json
{
  "permissions": [
    "core:default",
    "stronghold:default",
    "deep-link:default",
    "shell:allow-open",
    "notification:default"
  ]
}
```

### T4. Native secure storage — `tauri-plugin-stronghold` (или keyring)

Добавь в `Cargo.toml`:
```toml
tauri-plugin-stronghold = "2"
```
В `lib.rs`:
```rust
.plugin(tauri_plugin_stronghold::Builder::with_argon2(&app.path().app_local_data_dir().unwrap().join("stronghold.salt")).build())
```
Три `#[tauri::command]`:
- `session_get() -> Option<String>`
- `session_set(token: String)`
- `session_clear()`

На фронте — `apps/web/lib/tauri-session-storage.ts`:
```ts
import { invoke } from '@tauri-apps/api/core';
import type { SessionStorage } from '@mira/shared';
export const tauriSessionStorage: SessionStorage = {
  async get() { return await invoke<string | null>('session_get'); },
  async set(token) { await invoke('session_set', { token }); },
  async clear() { await invoke('session_clear'); },
};
```

После SessionStorage wiring (часть A) и T1 — desktop автоматически использует keyring.

### T5. Telegram Auth через deep-link

Telegram Login Widget работает только в браузере с зарегистрированным доменом. На desktop:

1. **Плагин:** `tauri-plugin-deep-link = "2"`. В `Cargo.toml` + `lib.rs` + capabilities.
2. **Схема:** `mira://` зарегистрировать в `tauri.conf.json`:
   ```json
   "plugins": {
     "deep-link": {
       "desktop": { "schemes": ["mira"] }
     }
   }
   ```
3. **Auth flow:**
   - Кнопка «Войти через Telegram» → `invoke('open_telegram_oauth', { returnTo: 'mira://auth' })` → открывает в системном браузере `https://oauth.telegram.org/auth?bot_id=...&origin=...&return_to=mira://auth`.
   - Браузер после успеха редиректит на `mira://auth?id=...&hash=...&...`.
   - Tauri ловит deep-link, отдаёт на фронт.
   - Фронт парсит query, вызывает `client.authenticate(params)`.
4. **Согласовать с владельцем бота:** добавить `mira://auth` в whitelisted return URLs в BotFather (если такая опция доступна — для приватного бота, возможно, неактуально).

Это самая сложная часть Tauri-интеграции. Если упрётся в Telegram настройки — оставь на потом и сделай T1-T4 без T5: desktop в mock-режиме будет работать, реальный auth можно делать через копирование токена из веб-сборки в keyring.

### T6. Tray UX — toggle вместо menu_on_left_click

`apps/desktop/src-tauri/src/lib.rs:20` — `menu_on_left_click(true)`. Привычнее: левый клик показывает/скрывает окно, правый — открывает меню. Заменить на:
```rust
.menu_on_left_click(false)
.on_tray_icon_event(|tray, event| { /* TrayIconEvent::Click → toggle window */ })
```
Вкусовщина — оставь как сейчас если не уверен.

### T7. (Опционально) Notifications для reminders

Когда сервер шлёт уведомление о напоминании (сейчас это в Telegram-бот идёт через `tools/scheduler.py`), desktop тоже мог бы показывать нативный toast через `tauri-plugin-notification`. Но это требует серверной поддержки доставки на desktop — пока за рамками v0.5.

---

## Часть C. Порядок работ v0.5

1. **v0.4.1** (полдня): B3R через вариант B + SessionStorage wiring (часть A).
2. **v0.5.0 desktop polish** (день):
   - T1 (IS_TAURI detection + conditional storage).
   - T2 (иконка-звезда).
   - T4 (stronghold плагин + invoke-команды + TauriSessionStorage).
   - T3 (capabilities).
3. **v0.5.1 desktop auth** (день, если Telegram пустит):
   - T5 (deep-link + Telegram OAuth).
   - Если упирается — заглушка с инструкцией для пользователя.
4. **Сборка bundle** для Linux (`.AppImage` + `.deb`), скриншоты окна. macOS/Windows — если есть к ним доступ.

---

## Часть D. Бэкенд-блокеры (без изменений)

Не сделано на бэкенде `mira_agent/web/app.py` (KimiCode не трогает):
- `CORSMiddleware` за env-флагом `MIRA_ALLOW_LOCAL_CORS=1`.
- `GET /history?session=...&limit=50`.
- `TELEGRAM_BOT_USERNAME` в `.env`.

Веб-клиент к ним готов, desktop тоже будет готов после T1+T4 (через тот же SessionStorage и `fetchHistory`).

---

## Часть E. Что НЕ делать в v0.5

- Streaming ответов LLM (бэкенд `providers.py`).
- Push-уведомления (FCM/APNS).
- Mobile (React Native).
- Голосовой ввод.
- Light theme.
- Свой экран настроек.
- Параллельный entry-point на Vite/standalone React, если можно обойтись conditional code в `apps/web` (T1 вариант a).

---

## Часть F. Сдача

После v0.4.1: новый zip, обновлённый `QUESTIONS.md` если есть вопросы (особенно по выбору вариант A vs B для B3R).

После v0.5.0: zip + Tauri-бандл (`.AppImage` или `.deb`), скриншот desktop-окна с активным треем, демонстрация native session storage (mock-режим достаточно).

После v0.5.1: Tauri-бандл с реальной Telegram-аутентификацией. Если уперлось в BotFather/return_to — отдельный `QUESTIONS.md` пункт с описанием проблемы.
