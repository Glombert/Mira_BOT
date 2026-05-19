# Брифинг v0.6 для KimiCode — ревью v0.5

**Контекст.** v0.5 закрыл багфиксы v0.4.1 (B3R через awaiter-queue в `MiraClient`, SessionStorage wiring) и Tauri-достройку (T1 conditional storage, T3 capabilities, T4 keyring-команды, T5 deep-link, T6 tray toggle). Реализация качественная. Клиентский MVP по факту завершён.

См. рядом `KIMI_REVIEW_v0.1.md` … `v0.4.md`, базовый контракт `API.md` / `design.md` / `KIMI_BRIEF.md`.

Это **короткий** брифинг — багфиксы и закрытие. Новых фич нет.

---

## Часть A. v0.5.1 — точечные правки

### T2-bug. Иконка — чёрная звезда вместо градиентной

**Файлы:** `apps/desktop/src-tauri/icons/*.png` (и `icon.icns`, `icon.ico`).

Сейчас сгенерированы из PNG, где звезда залита **сплошным чёрным** на тёмно-синем фоне. Должно быть: градиент `#FF8C42 → #FFB888` (см. `apps/web/components/ui/star-avatar.tsx` — `linearGradient` 0,0 → 28,28) на прозрачном фоне. В системном трее текущий вариант почти невидим на тёмных обоях.

**Чинить:** сделать корректный source 1024×1024 PNG с правильным fill и **transparent background**, прогнать через `npx @tauri-apps/cli icon path/to/star.png`. Проверить визуально хотя бы `128x128.png` после генерации.

### Q1. Awaiter cross-wiring между параллельными модалками

**Файл:** `packages/shared/src/api/mira-client.ts:391`.

`findIndex((a) => a.types.includes(msg.type))` — FCFS по очереди регистрации. Если в будущем две модалки одновременно зарегистрируют ожидание одного типа (`system`), первая по регистрации получит первый ответ — независимо от того, на чью команду он пришёл.

Сейчас не воспроизводится, потому что `ModalShell` открывает модалки по одной. Но это хрупкий инвариант — кто-нибудь добавит non-modal popover, который тоже ждёт ответ, и cross-wire случится.

**Чинить.** Хранить в `awaiter` саму команду, добавить в `_emit` лучший-матч поиск: предпочитать awaiter с самой свежей `sendCommand` (по timestamp). Полностью решит только серверный correlation-id, но это уже backend. Достаточно — документировать инвариант «одна модалка с awaitable за раз» в комментарии к `sendCommandAwait`.

### Q2. Deep-link auth — `auth_date` обязателен

**Файл:** `apps/web/components/chat/chat-page.tsx:322`.

```ts
auth_date: parsed.searchParams.get('auth_date') || String(Math.floor(Date.now() / 1000)),
```

Если `auth_date` не пришёл — fallback на `Date.now()`. Бесполезен: Telegram считал HMAC по своему `auth_date`, серверный `_verify_telegram` (`mira_agent/web/app.py:130-140`) проверит и вернёт `ok:false`. Лучше явно отбросить такой URL:

```ts
const auth_date = parsed.searchParams.get('auth_date');
if (!id || !hash || !auth_date) continue;
// ...
auth_date,
```

### Q3. README — оговорить требования keyring на Linux

**Файл:** `README.md` (корень репозитория клиента).

`keyring = "3"` на Linux работает через D-Bus secret-service. Требуется запущенный GNOME Keyring / KWallet / другой `org.freedesktop.secrets` сервис. На headless-серверах и минимальных WM без secret-service `keyring::Entry::set_password()` упадёт.

В README добавить раздел «Требования к Linux»:
- secret-service-совместимый агент (GNOME Keyring, KWallet, или `keyutils` для headless).
- системные dev-deps для сборки: `libgtk-3-dev libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev libsoup-3.0-dev`.

---

## Часть B. Бэкенд-блокеры закрыты владельцем

На момент сдачи v0.6: в `mira_agent/web/app.py` добавлены:

- `CORSMiddleware` под env-флагом `MIRA_ALLOW_LOCAL_CORS=1` — для dev `localhost:3000 → :8000`.
- `GET /history?session=...&limit=50` — клиент уже умеет его вызывать через `client.fetchHistory()`.
- В `.env` проставлен `TELEGRAM_BOT_USERNAME`.

После v0.5.1 фиксов нужно прогнать **end-to-end smoke test**:
1. Запустить бэкенд с `MIRA_ALLOW_LOCAL_CORS=1`.
2. Запустить веб с `NEXT_PUBLIC_MIRA_MOCK=false`.
3. Войти через реальный Telegram Login Widget.
4. Отправить сообщение, дождаться ответа.
5. Перезагрузить страницу — убедиться что история подгрузилась.
6. Открыть Cmd+K → выполнить `files`, `reminders` (внутри модалок), убедиться что нет дубликатов в чате.
7. Загрузить файл через paperclip + drag-and-drop — проверить прогресс и появление в `files`.

Если всё ок — обновить README с инструкцией по реальному запуску (не только mock), пересобрать архив.

---

## Часть C. Desktop bundle

Сборка `.AppImage` / `.deb` — задача владельца (нужны системные deps + Linux-хост). После сборки:
- Запустить, проверить что иконка-звезда правильная (часть A.T2).
- Войти через Telegram (deep-link на `mira://auth`).
- Закрыть окно — должно свернуться в трей.
- Перезапустить — keyring должен подгрузить токен, авторизация не должна запрашиваться повторно.

Если deep-link не срабатывает — проверить регистрацию схемы `mira://` в `~/.local/share/applications/mira-desktop.desktop` (Linux) или соответствующих местах для macOS/Windows.

---

## Часть D. Что НЕ делать в v0.6

- Streaming ответов LLM.
- Push-уведомления.
- React Native mobile.
- Голосовой ввод.
- Light theme.
- Новые UI-фичи — фокус на закрытие MVP, не на расширение.

---

## Часть E. Сдача

Один zip-архив v0.6 с:
- Веб-клиент с фиксами Q1, Q2 + правильная иконка (T2).
- README обновлён (Q3 + инструкция по реальному запуску).
- Скриншоты desktop-окна с **новой** иконкой в трее (если есть Linux-хост с deps).
- `QUESTIONS.md` — если возникли вопросы по smoke test или сборке.

После этого MVP считается закрытым. Следующие итерации — по запросу владельца.
