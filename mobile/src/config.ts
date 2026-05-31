// App version. Главный источник версии — package.json (его читает android/app/build.gradle
// для versionName). Здесь дублируется для рантайма (показывается на экране логина и
// в /mobile/version проверке обновлений). Поднимать одновременно с package.json.
export const APP_VERSION = '1.1.1';
// Production backend
export const BASE_URL = 'https://mira-bot.duckdns.org';
// For local dev emulator: http://10.0.2.2:8000
export const IS_MOCK = false;

// Telegram bot username (без @). Используется в Linking.openURL для
// «Войти через Telegram» и в подсказках. Должен совпадать с TELEGRAM_BOT_USERNAME
// на сервере и с тем, что зарегистрировано в @BotFather через /setdomain.
export const BOT_USERNAME = 'mira_changing_bot';
