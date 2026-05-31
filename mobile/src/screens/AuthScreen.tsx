import React, { useState, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  Image,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  StatusBar,
  Alert,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Linking,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import type { NativeStackNavigationProp } from '@react-navigation/native-stack';
import type { RootStackParamList } from '../navigation/AppNavigator';
import { MiraClient } from '../api/mira-client';
import { mobileSessionStorage } from '../utils/storage';
import { BASE_URL, BOT_USERNAME, IS_MOCK } from '../config';
import { colors, spacing, radii, typography } from '../theme';
import LinearGradient from 'react-native-linear-gradient';

export function AuthScreen() {
  const navigation = useNavigation<NativeStackNavigationProp<RootStackParamList>>();
  const insets = useSafeAreaInsets();
  const [client] = useState(() => new MiraClient({ baseUrl: BASE_URL, mock: IS_MOCK, sessionStorage: mobileSessionStorage }));
  const [loading, setLoading] = useState(false);
  const [token, setToken] = useState('');
  const [showManual, setShowManual] = useState(false);

  useEffect(() => {
    (async () => {
      const stored = await client.loadSession();
      if (stored) {
        navigation.replace('Chat');
      }
    })();
  }, [client, navigation]);

  const handleTelegramAuth = useCallback(async () => {
    // tg://resolve открывает Telegram-приложение напрямую, без браузерного хопа.
    // Если Telegram не установлен — Alert. Раньше был fallback на https://t.me/,
    // но https://t.me/ на некоторых устройствах сначала открывает браузер,
    // который потом перекидывает в Telegram — лишние тапы.
    const tgUrl = `tg://resolve?domain=${BOT_USERNAME}&start=login`;
    try {
      await Linking.openURL(tgUrl);
    } catch {
      Alert.alert(
        'Telegram не установлен',
        `Установи Telegram и открой @${BOT_USERNAME}, отправь /login`,
      );
    }
  }, []);

  const handleManualToken = useCallback(async () => {
    if (!token.trim()) return;
    setLoading(true);
    try {
      await client.setSession(token.trim());
      // Валидация: пробуем дёрнуть /history с этим токеном.
      // Если сервер не принял — это либо чужой токен, либо просрочка.
      await client.fetchHistory(1);
      navigation.replace('Chat');
    } catch (e) {
      await client.clearSession();
      Alert.alert('Неверный токен', 'Сервер не принял этот токен сессии. Проверь правильность или войди через Telegram.');
    } finally {
      setLoading(false);
    }
  }, [client, navigation, token]);

  const openTelegramBot = useCallback(() => {
    const botUrl = `https://t.me/${BOT_USERNAME}`;
    Linking.canOpenURL(botUrl).then((supported) => {
      if (supported) {
        Linking.openURL(botUrl);
      } else {
        Alert.alert('Не получилось открыть Telegram', `Установи Telegram и открой @${BOT_USERNAME}`);
      }
    });
  }, []);

  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#0a0a1a" />
      <LinearGradient colors={['#0a0a1a', '#1a1a3e', '#0f0f2a']} style={styles.gradient}>
        <KeyboardAvoidingView
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          style={styles.keyboardView}
        >
          <ScrollView
            contentContainerStyle={[
              styles.scroll,
              { paddingTop: insets.top + 20, paddingBottom: insets.bottom + 20 },
            ]}
            keyboardShouldPersistTaps="handled"
          >
            <View style={styles.avatarContainer}>
              <Image
                source={require('../assets/mira-avatar-full.png')}
                style={styles.avatar}
                resizeMode="cover"
              />
              <View style={styles.glow} />
            </View>

            <Text style={styles.title}>Мира</Text>
            <Text style={styles.subtitle}>Между космосом и сервером</Text>
            <Text style={styles.version}>βeta v0.6.0</Text>

            <View style={styles.card}>
              {loading ? (
                <ActivityIndicator size="large" color="#FF8C42" />
              ) : (
                <>
                  {!showManual ? (
                    <>
                      <TouchableOpacity style={styles.telegramButton} onPress={handleTelegramAuth}>
                        <Text style={styles.telegramButtonText}>📲 Войти через Telegram</Text>
                      </TouchableOpacity>
                      <Text style={styles.hint}>Авторизация через твой аккаунт Telegram</Text>

                      <TouchableOpacity style={styles.primaryButton} onPress={openTelegramBot}>
                        <Text style={styles.primaryButtonText}>🤖 Открыть бота</Text>
                      </TouchableOpacity>
                      <Text style={styles.hint}>Напиши /start боту @{BOT_USERNAME}</Text>

                      <TouchableOpacity style={styles.secondaryButton} onPress={() => setShowManual(true)}>
                        <Text style={styles.secondaryButtonText}>🔑 У меня есть токен</Text>
                      </TouchableOpacity>
                    </>
                  ) : (
                    <>
                      <Text style={styles.label}>Вставь токен сессии</Text>
                      <TextInput
                        style={styles.input}
                        value={token}
                        onChangeText={setToken}
                        placeholder="session_token..."
                        placeholderTextColor="#666"
                        autoCapitalize="none"
                        multiline
                        numberOfLines={3}
                      />
                      <TouchableOpacity style={styles.primaryButton} onPress={handleManualToken}>
                        <Text style={styles.primaryButtonText}>Войти</Text>
                      </TouchableOpacity>
                      <TouchableOpacity style={styles.textButton} onPress={() => setShowManual(false)}>
                        <Text style={styles.textButtonText}>← Назад</Text>
                      </TouchableOpacity>
                    </>
                  )}
                </>
              )}
            </View>
          </ScrollView>
        </KeyboardAvoidingView>
      </LinearGradient>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  gradient: { flex: 1 },
  keyboardView: { flex: 1 },
  scroll: {
    flexGrow: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: spacing.xl,
  },
  avatarContainer: {
    width: 160,
    height: 160,
    borderRadius: radii.pill,
    overflow: 'hidden',
    marginBottom: spacing.lg,
    position: 'relative',
    borderWidth: 2,
    borderColor: colors.gold.dim,
  },
  avatar: {
    width: 160,
    height: 160,
  },
  glow: {
    position: 'absolute',
    inset: 0,
    borderRadius: radii.pill,
    borderWidth: 3,
    borderColor: colors.gold.glow,
  },
  title: {
    fontSize: typography.welcomeGreeting.fontSize,
    fontWeight: typography.welcomeGreeting.fontWeight,
    color: colors.gold.DEFAULT,
    marginBottom: spacing.xs,
    letterSpacing: 2,
  },
  subtitle: {
    fontSize: typography.body.fontSize,
    color: colors.text.muted,
    textAlign: 'center',
  },
  version: {
    fontSize: typography.status.fontSize,
    color: colors.text.faint,
    marginBottom: spacing.xl,
    marginTop: spacing.xs,
  },
  card: {
    width: '100%',
    maxWidth: 360,
    backgroundColor: colors.bg.surface,
    borderRadius: radii.card,
    padding: spacing.xl,
    borderWidth: 1,
    borderColor: colors.border.subtle,
    gap: 10,
  },
  primaryButton: {
    backgroundColor: colors.gold.DEFAULT,
    borderRadius: radii.button,
    paddingVertical: 14,
    alignItems: 'center',
  },
  primaryButtonText: {
    color: colors.bg.page,
    fontWeight: '700',
    fontSize: typography.body.fontSize,
  },
  telegramButton: {
    backgroundColor: '#229ED9',
    borderRadius: radii.button,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: spacing.xs,
  },
  telegramButtonText: {
    color: '#fff',
    fontWeight: '700',
    fontSize: typography.body.fontSize,
  },
  secondaryButton: {
    backgroundColor: 'transparent',
    borderRadius: radii.button,
    paddingVertical: 14,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.border.subtle,
    marginTop: spacing.xs,
  },
  secondaryButtonText: {
    color: colors.gold.DEFAULT,
    fontWeight: '600',
    fontSize: typography.body.fontSize,
  },
  hint: {
    color: colors.text.dim,
    fontSize: typography.status.fontSize,
    textAlign: 'center',
    marginTop: -6,
    marginBottom: 6,
  },
  label: {
    color: colors.text.dim,
    fontSize: typography.body.fontSize,
    marginBottom: spacing.xs,
  },
  input: {
    backgroundColor: colors.bg.page,
    borderRadius: radii.sidebarItem,
    padding: spacing.md,
    color: colors.text.primary,
    fontSize: 13,
    borderWidth: 1,
    borderColor: colors.border.subtle,
    textAlignVertical: 'top',
  },
  textButton: {
    alignItems: 'center',
    paddingVertical: spacing.sm,
  },
  textButtonText: {
    color: colors.text.muted,
    fontSize: typography.body.fontSize,
  },
});
