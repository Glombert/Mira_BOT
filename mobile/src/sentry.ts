import * as Sentry from '@sentry/react-native';
import { SENTRY_DSN, APP_VERSION } from './config';

// Инициализация Sentry/Bugsink. Без DSN — полный no-op (ничего не шлём).
// Вызывается из index.js ДО рендера, чтобы ловить ранние ошибки.
let inited = false;

export function initSentry(): void {
  if (inited || !SENTRY_DSN) return;
  Sentry.init({
    dsn: SENTRY_DSN,
    release: `mira-mobile@${APP_VERSION}`,
    // Только ошибки — без перф-трейсинга/replay (экономно для self-hosted Bugsink).
    tracesSampleRate: 0,
    sendDefaultPii: false,
  });
  inited = true;
}

export { Sentry };
