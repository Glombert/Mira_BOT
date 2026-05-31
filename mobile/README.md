# Мира Mobile

React Native Android приложение для персонального ИИ-агента Мира.

**Версия:** 1.0.6 · **Дизайн:** Aurora (полночь + золото, шрифты Cormorant / Manrope / JetBrains Mono)

## Возможности

- 🎨 **Aurora UI** — тёмная тема, золотой акцент, фирменные SVG-иконки, живые анимации (дыхание аватара, мерцание, typewriter).
- 📲 **Обновление в приложении** — APK качается и ставится прямо в приложении, без браузера (как 2ГИС/Telegram).
- 📂 **Раскрывающиеся меню** — справочные команды (профиль, метрики, бэкапы, ритуалы, напоминания, задачи, Drive-статус, календарь) и список пользователей разворачиваются панелью прямо в боковом меню, не засоряя чат. Список пользователей → подменю действий (переименовать / статус / блок).
- ✂️ **Выделение и копирование** текста сообщений (long-press, как в Telegram).
- ⬇️ **Кнопка «вниз»** — быстрый прыжок к последним сообщениям.
- 🔗 Telegram-логин, вложения (до 5 файлов), Google Drive / Calendar / Sheets, напоминания и задачи, push-уведомления (FCM).

## Структура

```
MiraMobile/
├── android/              # Нативный Android проект
├── src/
│   ├── api/              # MiraClient (WS + HTTP + awaiters)
│   ├── assets/           # Аватар Миры + иконки
│   ├── components/       # UI компоненты
│   ├── navigation/       # React Navigation
│   ├── screens/          # AuthScreen, ChatScreen
│   ├── types/            # TypeScript типы
│   └── utils/            # хранилище сессии (Keychain)
├── App.tsx               # Корневой компонент
├── index.js              # Entry point
└── .github/workflows/    # CI/CD для сборки APK
```

## Требования для локальной сборки

- Node.js >= 22
- Android Studio с SDK (API 34, Build Tools 34.0.0)
- JDK 17
- `ANDROID_HOME` настроена

## Быстрый старт

```bash
cd MiraMobile
npm install
# Для Android эмулятора (localhost = 10.0.2.2)
npx react-native run-android
```

## Сборка APK

### Способ 1: GitHub Actions (рекомендуется)

Самый простой способ — собирать в облаке. Workflow уже настроен в `.github/workflows/build-apk.yml`.

**Как использовать:**
1. Скопируй папку `MiraMobile/` в репозиторий (например, `mira_agent/clients/mobile/`)
2. Скопируй `.github/workflows/build-apk.yml` в `.github/workflows/` репозитория
3. Открой GitHub → Actions → "Build Android APK" → Run workflow
4. Через ~15 минут APK появится в артефактах

**Ручной запуск с версией:**
- В интерфейсе GitHub Actions укажи `version` (например `0.6.0`)
- APK будет назван `mira-mobile-v0.6.0.apk`

### Способ 2: Локальная сборка

```bash
cd MiraMobile
npm install

cd android
# Debug
./gradlew assembleDebug
# Release (требует подпись)
./gradlew assembleRelease
```

APK debug: `android/app/build/outputs/apk/debug/app-debug.apk`
APK release: `android/app/build/outputs/apk/release/app-release.apk`

### Способ 3: Expo EAS (если мигрируем на Expo)

```bash
cd MiraMobile
npx install-expo-modules@latest
npx eas build --platform android --profile preview
```

## Особенности

- **Дизайн Aurora** — полночный фон `#0b1226` + золото `#f5bc7a`, шрифты Cormorant / Manrope / JetBrains Mono, фирменные SVG-иконки, анимации.
- **Аватар Миры** — портрет (зум в круг + мягкое гало) в шапке, пузырях, боковом меню, welcome-экране.
- **MiraClient** — `sendCommandAwait`, reconnect, сессия в Keychain (react-native-keychain).
- **Боковое меню** — справочные команды и список пользователей раскрываются панелью прямо в меню (не в чате); действия подтверждаются тостом.
- **Markdown** — ответы Миры с поддержкой Markdown; текст выделяется (long-press).
- **Файлы** — upload через `XMLHttpRequest`, вложения до 5 шт.

## Auth

Telegram-логин через deep-link (`miramobile://auth`): пользователь жмёт «Войти через Telegram», бот присылает одноразовую ссылку `/m/auth`, по тапу приложение получает сессию. Сессия хранится в Keychain.

## CI/CD

Workflow `.github/workflows/build-apk.yml`:
- Запускается вручную (`workflow_dispatch`) или при пуше в `main`
- Устанавливает JDK 17, Android SDK, Node.js
- Кеширует Gradle
- Собирает `assembleRelease`
- Выгружает APK как артефакт (хранится 30 дней)
