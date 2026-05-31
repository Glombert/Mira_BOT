import { Alert, Platform, Linking } from 'react-native';
import ReactNativeBlobUtil from 'react-native-blob-util';
import { APP_VERSION, BASE_URL } from '../config';

interface VersionInfo {
  version: string;
  apk_url: string;
  release_notes: string;
}

function compareVersions(a: string, b: string): number {
  const pa = a.split('.').map(Number);
  const pb = b.split('.').map(Number);
  for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
    const na = pa[i] || 0;
    const nb = pb[i] || 0;
    if (na > nb) return 1;
    if (na < nb) return -1;
  }
  return 0;
}

// Скачивание APK ВНУТРИ приложения (как 2ГИС/Telegram): системный загрузчик
// показывает прогресс в шторке, по завершении открываем установщик. Браузер
// в цепочке больше не участвует.
async function downloadAndInstall(apkUrl: string, version: string): Promise<void> {
  if (Platform.OS !== 'android') {
    // iOS не поддерживает sideload — фолбэк на внешнюю ссылку.
    Linking.openURL(apkUrl).catch(() => {});
    return;
  }
  try {
    const path = `${ReactNativeBlobUtil.fs.dirs.DownloadDir}/mira-${version}.apk`;
    Alert.alert(
      'Скачивание началось',
      'Прогресс виден в шторке уведомлений. По завершении откроется установка. Если Android спросит — разреши установку из приложения «Мира».'
    );
    const res = await ReactNativeBlobUtil.config({
      addAndroidDownloads: {
        useDownloadManager: true,
        notification: true,
        title: `Мира ${version}`,
        description: 'Скачивание обновления',
        mime: 'application/vnd.android.package-archive',
        mediaScannable: true,
        path,
      },
    }).fetch('GET', apkUrl);
    // Открыть системный установщик скачанного APK.
    ReactNativeBlobUtil.android.actionViewIntent(
      res.path(),
      'application/vnd.android.package-archive',
    );
  } catch {
    Alert.alert('Ошибка', 'Не удалось скачать обновление. Попробуй ещё раз позже.');
  }
}

export async function checkForUpdate(silent = false): Promise<void> {
  // fetch в RN игнорирует { timeout } — таймаут через AbortController.
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 5000);
  try {
    const res = await fetch(`${BASE_URL}/mobile/version`, { signal: ctrl.signal });
    clearTimeout(timer);
    if (!res.ok) {
      if (!silent) Alert.alert('Ошибка', 'Не удалось проверить обновления');
      return;
    }
    const data: VersionInfo = await res.json();

    if (compareVersions(data.version, APP_VERSION) > 0) {
      const notes = data.release_notes ? data.release_notes + '\n\n' : '';
      Alert.alert(
        `Доступно обновление ${data.version}`,
        notes + 'Скачаю и установлю прямо здесь — браузер не нужен.',
        [
          { text: 'Позже', style: 'cancel' },
          {
            text: 'Обновить',
            onPress: () => downloadAndInstall(data.apk_url, data.version),
          },
        ]
      );
    } else if (!silent) {
      Alert.alert('Обновлений нет', `Установлена актуальная версия ${APP_VERSION}`);
    }
  } catch (e: any) {
    clearTimeout(timer);
    if (!silent) {
      const msg = e?.name === 'AbortError'
        ? 'Сервер обновлений не ответил за 5 секунд'
        : 'Не удалось подключиться к серверу обновлений';
      Alert.alert('Ошибка', msg);
    }
  }
}
