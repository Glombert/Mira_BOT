import React, { useRef, useState, useCallback } from 'react';
import {
  View,
  StyleSheet,
  ActivityIndicator,
  Text,
  TouchableOpacity,
  Alert,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { WebView, WebViewNavigation } from 'react-native-webview';
import type { ShouldStartLoadRequest } from 'react-native-webview/lib/WebViewTypes';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/AppNavigator';
import { MiraClient } from '../api/mira-client';
import { mobileSessionStorage } from '../utils/storage';
import { BASE_URL } from '../config';

const AUTH_PAGE_URL = 'https://mira.maakhv.ru/auth/mobile';

// Только эти https-домены пускаем в WebView. Всё остальное — блок.
// telegram.org нужен для telegram-widget.js и виджета авторизации.
// mira-bot.duckdns.org — легаси-домен, жив на переходный период.
const ALLOWED_HOSTS = ['mira.maakhv.ru', 'mira-bot.duckdns.org', 'telegram.org', 'oauth.telegram.org'];

function parseDeepLinkToken(url: string): string | null {
  // miramobile://auth?token=XYZ — ручной парсинг,
  // т.к. URL-полифил в RN не всегда корректно работает с кастомными схемами.
  const match = url.match(/^miramobile:\/\/auth\?(?:.*&)?token=([^&]+)/);
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return null;
  }
}

function isAllowedHttpUrl(url: string): boolean {
  if (!url.startsWith('https://')) return false;
  try {
    const host = url.replace(/^https?:\/\//, '').split('/')[0].split(':')[0];
    return ALLOWED_HOSTS.some((h) => host === h || host.endsWith('.' + h));
  } catch {
    return false;
  }
}

export function TelegramAuthScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const insets = useSafeAreaInsets();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const webViewRef = useRef<WebView>(null);
  const consumedTokenRef = useRef(false);  // не принимаем токен дважды

  const completeAuth = useCallback(async (token: string) => {
    if (consumedTokenRef.current) return;
    consumedTokenRef.current = true;
    setSaving(true);
    const client = new MiraClient({ baseUrl: BASE_URL, mock: false, sessionStorage: mobileSessionStorage });
    try {
      await client.setSession(token);
      navigation.replace('Chat');
    } catch (e) {
      setSaving(false);
      consumedTokenRef.current = false;
      Alert.alert('Ошибка', 'Не удалось сохранить сессию');
    }
  }, [navigation]);

  // Фильтр всех попыток навигации: блокируем чужие хосты и перехватываем deep link.
  const onShouldStartLoadWithRequest = useCallback((req: ShouldStartLoadRequest): boolean => {
    const url = req.url || '';
    if (url.startsWith('miramobile://auth')) {
      const token = parseDeepLinkToken(url);
      if (token) completeAuth(token);
      return false;  // не даём WebView самому идти по этой схеме
    }
    if (url.startsWith('about:') || url === 'about:blank') return true;
    if (isAllowedHttpUrl(url)) return true;
    return false;  // всё остальное — режем
  }, [completeAuth]);

  // Дублирующая защёлка на случай если deep link придёт уже после navigation state change
  // (например, через setTimeout/window.location в JS виджета).
  const handleNavigationStateChange = useCallback((navState: WebViewNavigation) => {
    const url = navState.url || '';
    if (url.startsWith('miramobile://auth')) {
      const token = parseDeepLinkToken(url);
      if (token) completeAuth(token);
    }
  }, [completeAuth]);

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.toolbar}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Text style={styles.backText}>← Закрыть</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Вход через Telegram</Text>
        <View style={styles.spacer} />
      </View>
      {(loading || saving) && (
        <View style={styles.loader}>
          <ActivityIndicator size="large" color="#FF8C42" />
          <Text style={styles.loaderText}>
            {saving ? 'Сохраняю сессию...' : 'Загрузка...'}
          </Text>
        </View>
      )}
      {error && (
        <View style={styles.errorBox}>
          <Text style={styles.errorText}>{error}</Text>
          <TouchableOpacity
            style={styles.retryButton}
            onPress={() => {
              setError(null);
              setLoading(true);
              webViewRef.current?.reload();
            }}
          >
            <Text style={styles.retryText}>Повторить</Text>
          </TouchableOpacity>
        </View>
      )}
      <WebView
        ref={webViewRef}
        source={{ uri: AUTH_PAGE_URL }}
        style={[styles.webview, error ? styles.webviewHidden : null]}
        onLoadStart={() => setLoading(true)}
        onLoadEnd={() => setLoading(false)}
        onShouldStartLoadWithRequest={onShouldStartLoadWithRequest}
        onNavigationStateChange={handleNavigationStateChange}
        onError={(e) => {
          setLoading(false);
          const desc = e.nativeEvent?.description || 'Не удалось загрузить страницу';
          setError(`Ошибка загрузки: ${desc}`);
        }}
        onHttpError={(e) => {
          setLoading(false);
          setError(`HTTP ${e.nativeEvent?.statusCode}: страница недоступна`);
        }}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#0a0a1a' },
  toolbar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: '#0f0f2a',
    borderBottomWidth: 1,
    borderBottomColor: '#1a1a3e',
  },
  backText: { color: '#FF8C42', fontSize: 16 },
  title: { color: '#e0e0f0', fontSize: 16, fontWeight: '600' },
  spacer: { width: 60 },
  loader: {
    position: 'absolute',
    top: '50%',
    left: 0,
    right: 0,
    alignItems: 'center',
    zIndex: 10,
  },
  loaderText: { color: '#8888aa', marginTop: 12, fontSize: 14 },
  webview: { flex: 1 },
  webviewHidden: { opacity: 0 },
  errorBox: {
    margin: 24,
    padding: 20,
    backgroundColor: '#1a1a3e',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#FF8C4250',
    alignItems: 'center',
  },
  errorText: { color: '#e0e0f0', fontSize: 14, textAlign: 'center', marginBottom: 16 },
  retryButton: {
    backgroundColor: '#FF8C42',
    paddingHorizontal: 24,
    paddingVertical: 10,
    borderRadius: 10,
  },
  retryText: { color: '#0a0a1a', fontWeight: '700', fontSize: 14 },
});
