/**
 * Юнит-тесты мобильного MiraClient — чистая логика (сессии, WS-цикл,
 * маршрутизация, tech-канал, reconnect). Без нативных модулей: только мок WebSocket.
 * @format
 */
import { MiraClient } from '../src/api/mira-client';

class MockWebSocket {
  static OPEN = 1;
  static instances: MockWebSocket[] = [];
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];
  constructor(public url: string) { MockWebSocket.instances.push(this); }
  send(data: string) { this.sent.push(data); }
  close() { this.readyState = 3; }
  open() { this.readyState = MockWebSocket.OPEN; this.onopen && this.onopen(); }
  recv(obj: unknown) { this.onmessage && this.onmessage({ data: JSON.stringify(obj) }); }
  fireClose(code: number) { this.onclose && this.onclose({ code }); }
}

function memoryStorage() {
  let v: string | null = null;
  return {
    get: async () => v,
    set: async (t: string) => { v = t; },
    clear: async () => { v = null; },
  };
}

let WS_BACKUP: any;
beforeEach(() => {
  jest.useFakeTimers(); // чтобы ping-setInterval не утекал между тестами
  WS_BACKUP = (global as any).WebSocket;
  (global as any).WebSocket = MockWebSocket as any;
  MockWebSocket.instances = [];
});
afterEach(() => {
  jest.clearAllTimers();
  jest.useRealTimers();
  (global as any).WebSocket = WS_BACKUP;
});

const opts = { baseUrl: 'https://x.test', session: 'tok' };

describe('mobile MiraClient — сессия', () => {
  it('setSession/loadSession/clear через storage', async () => {
    const c = new MiraClient({ baseUrl: 'https://x.test', sessionStorage: memoryStorage() as any });
    expect(c.isAuthenticated()).toBe(false);
    await c.setSession('abc');
    expect(c.isAuthenticated()).toBe(true);
    expect(await c.loadSession()).toBe('abc');
    await c.clearSession();
    expect(c.isAuthenticated()).toBe(false);
  });
});

describe('mobile MiraClient — WS и маршрутизация', () => {
  it('connect → onopen → connected; on(ready) получает', async () => {
    const c = new MiraClient(opts);
    const p = c.connect();
    MockWebSocket.instances[0].open();
    await p;
    expect(c.connected).toBe(true);
    const got: any[] = [];
    c.on('ready', (m: any) => got.push(m));
    MockWebSocket.instances[0].recv({ type: 'ready', name: 'Andrey' });
    expect(got).toEqual([{ type: 'ready', name: 'Andrey' }]);
  });

  it('channel=tech → onTech, не в общие слушатели', async () => {
    const c = new MiraClient(opts);
    const p = c.connect();
    MockWebSocket.instances[0].open();
    await p;
    const chat: any[] = []; const tech: any[] = [];
    c.on('system', (m: any) => chat.push(m));
    c.onTech((e: any) => tech.push(e));
    MockWebSocket.instances[0].recv({ channel: 'tech', type: 'system', content: 't' });
    expect(tech.length).toBe(1);
    expect(chat.length).toBe(0);
  });

  it('sendCommandAwait резолвится на ожидаемый тип', async () => {
    const c = new MiraClient(opts);
    const p = c.connect();
    MockWebSocket.instances[0].open();
    await p;
    const a = c.sendCommandAwait('whoami', ['system'], 2000);
    MockWebSocket.instances[0].recv({ type: 'system', content: 'i' });
    await expect(a).resolves.toMatchObject({ type: 'system', content: 'i' });
  });

  it('close 4001 → auth_required', async () => {
    const c = new MiraClient(opts);
    const p = c.connect();
    MockWebSocket.instances[0].open();
    await p;
    const auth: any[] = [];
    c.on('auth_required', (m: any) => auth.push(m));
    MockWebSocket.instances[0].fireClose(4001);
    expect(auth.length).toBe(1);
  });

  it('reconnect() создаёт новое соединение', async () => {
    const c = new MiraClient(opts);
    const p = c.connect();
    MockWebSocket.instances[0].open();
    await p;
    const rp = c.reconnect();
    expect(MockWebSocket.instances.length).toBe(2);
    MockWebSocket.instances[1].open();
    await rp;
    expect(c.connected).toBe(true);
  });
});
