/**
 * FCM-регистрация: запрашиваем permission, получаем токен, шлём на сервер.
 *
 * Вызывается из ChatScreen сразу после успешного логина (когда session уже есть).
 * Идемпотентно: повторный вызов с тем же токеном просто обновит updated_at на сервере.
 *
 * Background-обработчик (приходит сообщение когда приложение убито) регистрируется
 * в index.js — RN требует чтобы он жил на самом верхнем уровне, до AppRegistry.
 */
import { Platform, PermissionsAndroid } from 'react-native';
import messaging from '@react-native-firebase/messaging';
import { BASE_URL } from '../config';

let _lastRegistered: string | null = null;

async function requestPermission(): Promise<boolean> {
  // Android 13+ требует runtime permission на POST_NOTIFICATIONS.
  if (Platform.OS === 'android' && (Platform.Version as number) >= 33) {
    const r = await PermissionsAndroid.request(
      PermissionsAndroid.PERMISSIONS.POST_NOTIFICATIONS,
    );
    if (r !== PermissionsAndroid.RESULTS.GRANTED) return false;
  }
  // iOS / старый Android — Firebase messaging вернёт authorized или denied.
  const status = await messaging().requestPermission();
  return (
    status === messaging.AuthorizationStatus.AUTHORIZED ||
    status === messaging.AuthorizationStatus.PROVISIONAL
  );
}

export async function registerFcm(session: string): Promise<void> {
  try {
    const ok = await requestPermission();
    if (!ok) return;

    const fcmToken = await messaging().getToken();
    if (!fcmToken) return;

    // Если этот же токен мы уже зарегистрировали за сессию приложения — пропуск.
    // (Server при повторе просто обновит updated_at, но лишний запрос не нужен.)
    if (_lastRegistered === fcmToken) return;

    const res = await fetch(`${BASE_URL}/m/register_push_token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session,
        fcm_token: fcmToken,
        platform: Platform.OS,
      }),
    });
    if (res.ok) {
      _lastRegistered = fcmToken;
    }
  } catch {
    // FCM-регистрация не должна блокировать вход в чат — глотаем.
  }

  // Реакция на обновление токена (Firebase периодически ротирует).
  messaging().onTokenRefresh(async (newToken: string) => {
    try {
      await fetch(`${BASE_URL}/m/register_push_token`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session, fcm_token: newToken, platform: Platform.OS }),
      });
      _lastRegistered = newToken;
    } catch {}
  });
}
