// App version. Главный источник версии — package.json (его читает android/app/build.gradle
// для versionName). Здесь дублируется для рантайма (показывается на экране логина и
// в /mobile/version проверке обновлений). Поднимать одновременно с package.json.
export const APP_VERSION = '1.2.4';
// Production backend
export const BASE_URL = 'https://mira.maakhv.ru';
// For local dev emulator: http://10.0.2.2:8000
export const IS_MOCK = false;

// Telegram bot username (без @). Используется в Linking.openURL для
// «Войти через Telegram» и в подсказках. Должен совпадать с TELEGRAM_BOT_USERNAME
// на сервере и с тем, что зарегистрировано в @BotFather через /setdomain.
export const BOT_USERNAME = 'mira_changing_bot';

// Bugsink (self-hosted, Sentry-совместимый) DSN мобильного проекта.
// Ingest-ключ — клиентский (он всё равно в APK), прятать в репо смысла нет.
// Пусто → Sentry выключен (no-op).
export const SENTRY_DSN = 'https://8798b4a0820c4dd7993fd1739686b4c3@errors.maakhv.ru/2';
