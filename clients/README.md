# Mira Clients v0.6

Монорепозиторий клиентов для персонального ИИ-агента Мира.

## Структура

```
mira-clients/
├── packages/shared/        # Общие типы + MiraClient (HTTP + WS + upload)
├── apps/web/               # Next.js 14 веб-приложение (Tauri-aware)
├── apps/desktop/           # Tauri v2 desktop shell
└── screenshots/            # Скриншоты
```

## Быстрый старт

### Web (mock-режим)

```bash
cd mira-clients
npm install
NEXT_PUBLIC_MIRA_MOCK=true npm run dev:web
```

### Web (реальный бэкенд)

```bash
# 1. Запустить бэкенд с CORS для dev:
#    MIRA_ALLOW_LOCAL_CORS=1 python -m web.app
# 2. Запустить фронт:
npm run dev:web
```

### Desktop (Tauri)

```bash
npm run build:web        # собрать web bundle
cd apps/desktop
cargo tauri build        # собрать desktop бандл (.AppImage / .deb)
```

## Переменные окружения

| Переменная | Описание | По умолчанию |
|---|---|---|
| `NEXT_PUBLIC_MIRA_URL` | Базовый URL бэкенда | `http://localhost:8000` |
| `NEXT_PUBLIC_BOT_USERNAME` | Username Telegram-бота | `MiraTestBot` |
| `NEXT_PUBLIC_MIRA_MOCK` | Включить мок-режим | `false` |

## Требования к Linux (desktop)

### Сборка

```bash
sudo apt update
sudo apt install libgtk-3-dev libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev libsoup-3.0-dev
```

### Runtime (keyring)

Desktop использует `keyring = "3"`, который на Linux работает через D-Bus secret-service. Требуется запущенный secret-service-совместимый агент:

- **GNOME** / **Cinnamon** / **XFCE** — обычно уже есть (GNOME Keyring / Seahorse).
- **KDE** — KWallet с поддержкой FreedesktopSecret.
- **Headless / минимальный WM** — установите и запустите `gnome-keyring-daemon` или используйте `keyutils`:
  ```bash
  sudo apt install gnome-keyring
  eval $(gnome-keyring-daemon --start --components=secrets)
  export GNOME_KEYRING_CONTROL
  ```

Если secret-service недоступен, `session_set` вернёт ошибку и сессия не сохранится между перезапусками.

## Функционал v0.6

### Web (полный MVP)
- Чат: авторизация (Telegram Login Widget), WS, Markdown, история, reconnect
- Файлы: upload, drag-and-drop, прогресс, скачивание
- Command Palette (Cmd+K / Ctrl+K): 15+ команд с формами
- Модалки: профиль, напоминания, Google Drive (с ожиданием ответа, без дубликатов в чате)
- Mobile bottom sheets
- **SessionStorage wiring:** `webSessionStorage` через `localStorage`, `TauriSessionStorage` через native keyring

### Desktop (Tauri v2)
- Окно WebView загружает web bundle
- **Иконка:** звезда Миры (градиент `#FF8C42 → #FFB888`) на прозрачном фоне
- **Системный трей:** левый клик — показать/скрыть окно, правый клик — меню (Открыть / Выход)
- При закрытии окна — минимизация в трей
- **Native secure storage:** `session_get` / `session_set` / `session_clear` через системный keyring
- **Deep-link:** схема `mira://`, фронт обрабатывает `mira://auth?id=...&hash=...&auth_date=...` для Telegram OAuth

## Правки v0.4.1

- **B3R:** модальные ответы больше не дублируются в чат — `MiraClient` использует приоритетную очередь `awaiters` (first-come-first-served)
- **SessionStorage wiring:** убраны прямые вызовы `localStorage` из `chat-page.tsx`

## Правки v0.5.0

- **T1:** `IS_TAURI` runtime detection + conditional storage
- **T2:** иконка-звезда для Tauri
- **T3:** capabilities обновлены
- **T4:** native secure storage через `keyring` crate
- **T5:** deep-link плагин + обработчик `onOpenUrl`
- **T6:** tray UX — toggle окна левым кликом

## Правки v0.5.1 / v0.6

- **T2-bug:** иконка перегенерирована — прозрачный фон + корректный градиент звезды
- **Q1:** документирован инвариант «одна модалка с awaitable за раз» в `sendCommandAwait`
- **Q2:** deep-link `auth_date` больше не подменяется `Date.now()` — отсутствие параметра = отбрасывание URL
- **Q3:** README дополнен требованиями Linux (dev-deps + secret-service runtime)
