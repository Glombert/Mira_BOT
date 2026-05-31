import * as Keychain from 'react-native-keychain';
import AsyncStorage from '@react-native-async-storage/async-storage';
import type { SessionStorage } from '../types';

// Сессионный токен лежит ТОЛЬКО в системном keystore (Android Keystore / iOS Keychain).
// AsyncStorage больше не используется для токенов. Legacy-миграция оставлена
// на случай обновления с версий < 0.6.x.

const SERVICE = 'mira_session';
const LEGACY_KEY = 'mira_session';

async function migrateLegacy(): Promise<string | null> {
  try {
    const old = await AsyncStorage.getItem(LEGACY_KEY);
    if (!old) return null;
    await Keychain.setGenericPassword('session', old, { service: SERVICE });
    await AsyncStorage.removeItem(LEGACY_KEY);
    return old;
  } catch {
    return null;
  }
}

export const mobileSessionStorage: SessionStorage = {
  async get() {
    try {
      const creds = await Keychain.getGenericPassword({ service: SERVICE });
      if (creds && creds.password) return creds.password;
    } catch {
      // keychain недоступен — пробуем мигрировать из старого хранилища
    }
    return await migrateLegacy();
  },
  async set(token: string) {
    // Только Keychain — никакого AsyncStorage fallback.
    // Если Keychain недоступен, сессия не сохраняется и пользователь
    // увидит auth screen при следующем запуске.
    await Keychain.setGenericPassword('session', token, { service: SERVICE });
  },
  async clear() {
    try { await Keychain.resetGenericPassword({ service: SERVICE }); } catch { /* ignore */ }
    try { await AsyncStorage.removeItem(LEGACY_KEY); } catch { /* ignore */ }
  },
};
