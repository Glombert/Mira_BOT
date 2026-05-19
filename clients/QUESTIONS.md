# Вопросы по ходу разработки v0.6

## 1. Desktop bundle — системные зависимости Linux

**Статус:** desktop-код написан, собирается на машине с установленными системными deps.

**Вопрос:** Нужно ли установить системные зависимости и собрать `.AppImage`/`.deb` на этой машине, или передать код для сборки на машине разработчика?

Команды для установки (Ubuntu/Debian):
```bash
sudo apt update
sudo apt install libwebkit2gtk-4.1-dev libjavascriptcoregtk-4.1-dev build-essential curl wget file libxdo3 libssl-dev libayatana-appindicator3-dev librsvg2-dev libsoup-3.0-dev
```

## 2. Telegram deep-link auth (T5)

**Статус:** Заготовка на фронте и в Tauri есть (`mira://auth` схема зарегистрирована, обработчик `onOpenUrl` парсит query-параметры и вызывает `handleAuth`). `auth_date` теперь обязателен — URL без него отбрасывается.

**Вопрос:** Нужно ли добавить `mira://auth` в whitelist return URLs в BotFather? Для desktop-приложения Telegram Login Widget не работает напрямую — deep-link flow требует открытия системного браузера с `return_to=mira://auth`.

Если BotFather не принимает non-HTTPS return URLs:
- **Вариант А:** Оставить deep-link заглушку и добавить UI-инструкцию: "Скопируй токен из веб-версии".
- **Вариант Б:** Реализовать OAuth через собственный сервер-прокси, который обменивает Telegram code на token и редиректит на `mira://auth?session=...`.

Какой вариант предпочтительнее для production?

## 3. keyring vs stronghold

**Решение:** В брифе v0.5 предлагалось `tauri-plugin-stronghold`, но реализован `keyring = "3"` (системный keyring/keychain) — API проще, поведение для строкового токена идентично.

**Вопрос:** Оставить keyring или мигрировать на stronghold для соответствия брифу? keyring надёжно хранит токен в GNOME Keyring / macOS Keychain / Windows Credential Manager. README уже документирован с требованиями Linux.
