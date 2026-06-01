/**
 * Тесты офлайн-кэша истории (AsyncStorage мокается in-memory).
 * @format
 */
let mockStore: Record<string, string> = {};
jest.mock('@react-native-async-storage/async-storage', () => ({
  getItem: jest.fn(async (k: string) => (k in mockStore ? mockStore[k] : null)),
  setItem: jest.fn(async (k: string, v: string) => { mockStore[k] = v; }),
  removeItem: jest.fn(async (k: string) => { delete mockStore[k]; }),
}));

import {
  loadCachedHistory,
  saveCachedHistory,
  clearCachedHistory,
} from '../src/utils/historyCache';

const msg = (id: string, type: any = 'message', content = 'x'): any => ({
  id, type, content, timestamp: 1,
});

beforeEach(() => { mockStore = {}; });

describe('historyCache', () => {
  it('save → load возвращает те же финальные сообщения', async () => {
    const items = [msg('1', 'user'), msg('2', 'message')];
    await saveCachedHistory(items);
    expect(await loadCachedHistory()).toEqual(items);
  });

  it('пустой кэш → []', async () => {
    expect(await loadCachedHistory()).toEqual([]);
  });

  it('не кэширует thinking/thought', async () => {
    await saveCachedHistory([msg('1', 'message'), msg('2', 'thinking'), msg('3', 'thought')]);
    const loaded = await loadCachedHistory();
    expect(loaded.map((m: any) => m.id)).toEqual(['1']);
  });

  it('ограничивает кэш последними 50', async () => {
    const many = Array.from({ length: 70 }, (_, i) => msg(String(i)));
    await saveCachedHistory(many);
    const loaded = await loadCachedHistory();
    expect(loaded.length).toBe(50);
    expect(loaded[0].id).toBe('20'); // последние 50 → с 20-го
    expect(loaded[49].id).toBe('69');
  });

  it('clear → пусто', async () => {
    await saveCachedHistory([msg('1')]);
    await clearCachedHistory();
    expect(await loadCachedHistory()).toEqual([]);
  });

  it('битые данные → [] (не падает)', async () => {
    mockStore['mira:chatHistory'] = '{не json';
    expect(await loadCachedHistory()).toEqual([]);
  });

  it('не затирает кэш пустотой (в messages только thinking)', async () => {
    await saveCachedHistory([msg('1', 'message')]);
    await saveCachedHistory([msg('2', 'thinking')]); // persistable пуст → пропуск
    const loaded = await loadCachedHistory();
    expect(loaded.map((m: any) => m.id)).toEqual(['1']);
  });
});
