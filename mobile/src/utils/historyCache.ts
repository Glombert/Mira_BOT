import AsyncStorage from '@react-native-async-storage/async-storage';
import type { ChatMessageItem } from '../types';

// Офлайн-кэш истории чата: при открытии приложения показываем сразу, не дожидаясь
// сети/реконнекта. Сервер потом присылает свою историю и заменяет кэш.

const KEY = 'mira:chatHistory';
const MAX = 50; // ограничиваем размер, чтобы кэш не разрастался

export async function loadCachedHistory(): Promise<ChatMessageItem[]> {
  try {
    const raw = await AsyncStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export async function saveCachedHistory(messages: ChatMessageItem[]): Promise<void> {
  try {
    // Кэшируем только финальные сообщения (не «думает»/«мысль»), последние MAX.
    const persistable = messages
      .filter((m) => m.type !== 'thinking' && m.type !== 'thought')
      .slice(-MAX);
    // Не затираем кэш пустотой: когда в messages на миг только «думает»/«мысль»
    // (свежий чат, начало ответа), persistable пуст — иначе теряем историю.
    if (persistable.length === 0) return;
    await AsyncStorage.setItem(KEY, JSON.stringify(persistable));
  } catch {
    // не критично — кэш опционален
  }
}

export async function clearCachedHistory(): Promise<void> {
  try {
    await AsyncStorage.removeItem(KEY);
  } catch {
    // ignore
  }
}
