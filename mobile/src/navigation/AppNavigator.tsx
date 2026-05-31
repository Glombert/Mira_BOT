import React, { useEffect, useRef } from 'react';
import { Linking, Alert } from 'react-native';
import {
  NavigationContainer,
  createNavigationContainerRef,
} from '@react-navigation/native';
import { createNativeStackNavigator } from '@react-navigation/native-stack';
import { AuthScreen } from '../screens/AuthScreen';
import { ChatScreen } from '../screens/ChatScreen';
import { TelegramAuthScreen } from '../screens/TelegramAuthScreen';
import { TechScreen } from '../screens/TechScreen';
import { mobileSessionStorage } from '../utils/storage';

export type RootStackParamList = {
  Auth: undefined;
  Chat: undefined;
  TelegramAuth: undefined;
  Tech: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();
const navigationRef = createNavigationContainerRef<RootStackParamList>();

function parseTokenFromUrl(url: string | null): string | null {
  if (!url) return null;
  const match = url.match(/^miramobile:\/\/auth\?(?:.*&)?token=([^&]+)/);
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return null;
  }
}

// Анти-двойной-обработчик: если событие пришло дважды (initial-url + listener),
// принимаем токен только один раз.
const consumedTokens = new Set<string>();

async function handleAuthDeepLink(url: string | null) {
  const token = parseTokenFromUrl(url);
  if (!token) return;
  if (consumedTokens.has(token)) return;
  consumedTokens.add(token);
  try {
    await mobileSessionStorage.set(token);
    if (navigationRef.isReady()) {
      navigationRef.reset({ index: 0, routes: [{ name: 'Chat' }] });
    }
  } catch (e) {
    Alert.alert('Ошибка', 'Не удалось сохранить сессию из ссылки.');
  }
}

export function AppNavigator() {
  // Cold-start: app открыли тапом по deeplink из Telegram-кнопки.
  // Hot: app уже жил, deeplink приходит через addEventListener.
  const initialHandled = useRef(false);

  useEffect(() => {
    (async () => {
      if (initialHandled.current) return;
      initialHandled.current = true;
      const initial = await Linking.getInitialURL();
      handleAuthDeepLink(initial);
    })();

    const sub = Linking.addEventListener('url', (e) => {
      handleAuthDeepLink(e.url);
    });
    return () => sub.remove();
  }, []);

  return (
    <NavigationContainer ref={navigationRef}>
      <Stack.Navigator
        screenOptions={{
          headerShown: false,
          animation: 'fade',
        }}
        initialRouteName="Auth"
      >
        <Stack.Screen name="Auth" component={AuthScreen} />
        <Stack.Screen name="Chat" component={ChatScreen} />
        <Stack.Screen name="TelegramAuth" component={TelegramAuthScreen} />
        <Stack.Screen name="Tech" component={TechScreen} />
      </Stack.Navigator>
    </NavigationContainer>
  );
}
