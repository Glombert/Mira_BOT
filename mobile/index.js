/**
 * @format
 */

import { AppRegistry } from 'react-native';
import messaging from '@react-native-firebase/messaging';
import App from './App';
import { name as appName } from './app.json';
import { initSentry } from './src/sentry';

// Сбор ошибок (Bugsink) — до регистрации приложения, чтобы ловить ранние краши.
initSentry();

// Background message handler. Firebase требует регистрировать ДО AppRegistry —
// иначе при доставке push'а с закрытым приложением Android не найдёт хендлер.
// Тело — пустой no-op: уведомление само отрисовывается из notification-поля
// сообщения (см. server tools/fcm_tools.py). Здесь можно было бы делать
// бэкграунд-работу, но нам ничего такого не нужно.
messaging().setBackgroundMessageHandler(async () => {});

AppRegistry.registerComponent(appName, () => App);
