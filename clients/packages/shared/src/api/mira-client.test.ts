import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { MiraClient } from './mira-client';
import type { SessionStorage } from '../types/session-storage';

// --- Мок WebSocket: тест сам триггерит onopen/onmessage/onclose ---
class MockWebSocket {
  static OPEN = 1;
  static instances: MockWebSocket[] = [];
  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;
  onerror: (() => void) | null = null;
  sent: string[] = [];
  constructor(public url: string) {
    MockWebSocket.instances.push(this);
  }
  send(data: string) { this.sent.push(data); }
  close() { this.readyState = 3; }
  // helpers
  open() { this.readyState = MockWebSocket.OPEN; this.onopen?.(); }
  recv(obj: unknown) { this.onmessage?.({ data: JSON.stringify(obj) }); }
  fireClose(code: number) { this.onclose?.({ code }); }
}

function memoryStorage(): SessionStorage {
  let v: string | null = null;
  return {
    get: async () => v,
    set: async (t: string) => { v = t; },
    clear: async () => { v = null; },
  };
}

let WS_BACKUP: unknown;
beforeEach(() => {
  WS_BACKUP = (globalThis as any).WebSocket;
  (globalThis as any).WebSocket = MockWebSocket as unknown as typeof WebSocket;
  MockWebSocket.instances = [];
});
afterEach(() => {
  (globalThis as any).WebSocket = WS_BACKUP;
  vi.restoreAllMocks();
});

const opts = { baseUrl: 'https://x.test', session: 'tok' };

describe('MiraClient — сессия', () => {
  it('setSession/loadSession/clear через storage', async () => {
    const c = new MiraClient({ baseUrl: 'https://x.test', sessionStorage: memoryStorage() });
    expect(c.isAuthenticated()).toBe(false);
    await c.setSession('abc');
    expect(c.isAuthenticated()).toBe(true);
    expect(await c.loadSession()).toBe('abc');
    await c.clearSession();
    expect(c.isAuthenticated()).toBe(false);
  });
});

describe('MiraClient — WS жизненный цикл и маршрутизация', () => {
  it('connect → onopen → connected, on(ready) получает сообщение', async () => {
    const c = new MiraClient(opts);
    const p = c.connect();
    const ws = MockWebSocket.instances[0];
    ws.open();
    await p;
    expect(c.connected).toBe(true);

    const got: any[] = [];
    c.on('ready', (m) => got.push(m));
    ws.recv({ type: 'ready', name: 'Andrey' });
    expect(got).toEqual([{ type: 'ready', name: 'Andrey' }]);
  });

  it('сообщения channel=tech идут в onTech, не в общие слушатели', async () => {
    const c = new MiraClient(opts);
    const p = c.connect();
    MockWebSocket.instances[0].open();
    await p;
    const chat: any[] = []; const tech: any[] = [];
    c.on('system', (m) => chat.push(m));
    c.onTech((e) => tech.push(e));
    MockWebSocket.instances[0].recv({ channel: 'tech', type: 'system', content: 'tech-msg' });
    expect(tech.length).toBe(1);
    expect(chat.length).toBe(0);
  });

  it('sendCommandAwait резолвится на сообщение ожидаемого типа', async () => {
    const c = new MiraClient(opts);
    const p = c.connect();
    MockWebSocket.instances[0].open();
    await p;
    const await1 = c.sendCommandAwait('whoami', ['system'], 2000);
    MockWebSocket.instances[0].recv({ type: 'system', content: 'инфо' });
    await expect(await1).resolves.toMatchObject({ type: 'system', content: 'инфо' });
  });

  it('close 4001 → emit auth_required', async () => {
    const c = new MiraClient(opts);
    const p = c.connect();
    MockWebSocket.instances[0].open();
    await p;
    const auth: any[] = [];
    c.on('auth_required', (m) => auth.push(m));
    MockWebSocket.instances[0].fireClose(4001);
    expect(auth.length).toBe(1);
  });
});

describe('MiraClient — reconnect()', () => {
  it('reconnect() создаёт новое соединение', async () => {
    const c = new MiraClient(opts);
    const p = c.connect();
    MockWebSocket.instances[0].open();
    await p;
    expect(MockWebSocket.instances.length).toBe(1);

    const rp = c.reconnect();
    expect(MockWebSocket.instances.length).toBe(2); // новый сокет
    MockWebSocket.instances[1].open();
    await rp;
    expect(c.connected).toBe(true);
  });
});

describe('MiraClient — sendMessage/sendCommand', () => {
  it('sendMessage шлёт content (+attachments/mode)', async () => {
    const c = new MiraClient(opts);
    const p = c.connect();
    const ws = MockWebSocket.instances[0];
    ws.open();
    await p;
    c.sendMessage('привет', ['a.txt'], 'tech');
    const payload = JSON.parse(ws.sent.at(-1)!);
    expect(payload).toMatchObject({ content: 'привет', attachments: ['a.txt'], mode: 'tech' });
  });
});
