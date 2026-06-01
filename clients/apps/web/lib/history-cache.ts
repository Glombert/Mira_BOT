import type { ChatMessageItem } from '@/components/chat/chat-message';

// Офлайн-кэш истории чата (localStorage): показываем мгновенно при открытии,
// не дожидаясь WS/реконнекта. Сервер потом присылает свою историю и заменяет.

const KEY = 'mira:chatHistory';
const MAX = 50;

export function loadCachedHistory(): ChatMessageItem[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveCachedHistory(messages: ChatMessageItem[]): void {
  if (typeof window === 'undefined') return;
  try {
    const persistable = messages
      .filter((m) => m.type !== 'thinking' && m.type !== 'thought')
      .slice(-MAX);
    // Не затираем кэш пустотой: когда в messages на миг только «думает»/«мысль»
    // (свежий чат, начало ответа), persistable пуст — иначе теряем историю.
    if (persistable.length === 0) return;
    window.localStorage.setItem(KEY, JSON.stringify(persistable));
  } catch {
    // не критично
  }
}

export function clearCachedHistory(): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    // ignore
  }
}
