import type {
  TelegramAuthData,
  AuthResult,
  HealthStatus,
  HistoryResult,
  UploadResult,
  ServerMessage,
  ClientMessage,
  ProfileForm,
  OwnerInboxItem,
  TechEvent,
} from '../types';
import type { SessionStorage } from '../types/session-storage';

type MessageHandler<T extends ServerMessage['type']> = (
  msg: Extract<ServerMessage, { type: T }>
) => void;

export interface MiraClientOptions {
  baseUrl: string;
  session?: string;
  mock?: boolean;
  sessionStorage?: SessionStorage;
}

const FIXTURES: Record<string, unknown> = {
  health: { status: 'ok', bot_alive: true, web_alive: true },
  auth_telegram_success: {
    ok: true,
    session: '12345:Andrey:1715692800:abcdef1234567890abcdef1234567890',
    name: 'Andrey',
    is_new: false,
  },
  auth_telegram_failure: { ok: false, error: 'Ошибка авторизации' },
  history: {
    messages: [],
  },
  ws_ready: { type: 'ready', name: 'Andrey' },
  ws_auth_required: { type: 'auth_required', bot: 'MiraTestBot' },
  ws_pong: { type: 'pong' },
  ws_thinking: { type: 'thinking' },
  ws_message_simple: {
    type: 'message',
    content: 'Привет, Андрей. Чем могу помочь сегодня?',
  },
  ws_message_markdown: {
    type: 'message',
    content:
      'Готово. Я создала файл `report.xlsx` в `output/`. Вот краткая сводка:\n\n- **Строк:** 142\n- **Колонок:** 8\n- **Период:** январь-март 2026\n\nСкачать можно [по ссылке](/files/output/report.xlsx).',
  },
  ws_message_rate_limited: {
    type: 'message',
    content:
      'Эй, помедленнее — я ещё не успеваю отвечать. Подожди 24 сек и продолжим.',
  },
  ws_system_history_cleared: { type: 'system', content: 'История очищена.' },
  ws_system_whoami: {
    type: 'system',
    content:
      'Имя: Andrey\nСтатус: owner\nGoogle Drive: andrey@gmail.com\n\nЧто Мира знает о тебе:\nРаботает над проектом Mira_BOT. Любит лаконичные ответы. Часто работает по вечерам.',
  },
  ws_error_llm_failed: {
    type: 'error',
    content: 'Что-то пошло не так. Попробуй ещё раз.',
  },
  upload_success: { ok: true, filename: 'report.xlsx', size: 12345 },
};

export class MiraClient {
  private baseUrl: string;
  private session: string | null;
  private mock: boolean;
  private ws: WebSocket | null = null;
  private listeners: Map<string, Set<(msg: ServerMessage) => void>> = new Map();
  private techListeners: Set<(ev: TechEvent) => void> = new Set();
  private awaiters: Array<{
    types: ServerMessage['type'][];
    resolve: (msg: ServerMessage) => void;
  }> = [];
  private pingInterval: ReturnType<typeof setInterval> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempts = 0;
  private maxReconnectDelay = 30000;
  private _connected = false;
  private _connecting = false;
  private _manualDisconnect = false;
  private _sessionStorage?: SessionStorage;

  constructor(options: MiraClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/$/, '');
    this.session = options.session || null;
    this.mock = options.mock || false;
    this._sessionStorage = options.sessionStorage;
  }

  // Auth
  async authenticate(telegramData: TelegramAuthData): Promise<AuthResult> {
    if (this.mock) {
      await this._delay(300);
      return FIXTURES.auth_telegram_success as AuthResult;
    }
    const params = new URLSearchParams(telegramData as unknown as Record<string, string>);
    const res = await fetch(`${this.baseUrl}/auth/telegram?${params}`);
    return (await res.json()) as AuthResult;
  }

  // Авторизация из Telegram Mini App: подписанный initData вместо виджета.
  async authenticateWebApp(initData: string): Promise<AuthResult> {
    if (this.mock) {
      await this._delay(300);
      return FIXTURES.auth_telegram_success as AuthResult;
    }
    const res = await fetch(`${this.baseUrl}/auth/webapp`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ init_data: initData }),
    });
    return (await res.json()) as AuthResult;
  }

  async setSession(token: string): Promise<void> {
    this.session = token;
    if (this._sessionStorage) {
      await this._sessionStorage.set(token);
    }
  }

  async loadSession(): Promise<string | null> {
    // КРИТИЧНО: загруженный токен сразу присваиваем this.session.
    // Без этого connect()/fetchHistory()/uploadFile() будут строить URL
    // с пустым ?session= (this.session = null, хотя в storage токен есть).
    if (this._sessionStorage) {
      const stored = await this._sessionStorage.get();
      if (stored) this.session = stored;
      return stored;
    }
    return this.session;
  }

  async clearSession(): Promise<void> {
    this.session = null;
    if (this._sessionStorage) {
      await this._sessionStorage.clear();
    }
  }

  isAuthenticated(): boolean {
    return !!this.session;
  }

  // Health
  async health(): Promise<HealthStatus> {
    if (this.mock) {
      await this._delay(200);
      return FIXTURES.health as HealthStatus;
    }
    const res = await fetch(`${this.baseUrl}/health`);
    return (await res.json()) as HealthStatus;
  }

  // Upload
  uploadFile(
    file: File,
    onProgress?: (pct: number) => void
  ): Promise<UploadResult> {
    if (this.mock) {
      return new Promise((resolve) => {
        let pct = 0;
        const interval = setInterval(() => {
          pct += 20;
          if (onProgress) onProgress(pct);
          if (pct >= 100) {
            clearInterval(interval);
            resolve(FIXTURES.upload_success as UploadResult);
          }
        }, 300);
      });
    }
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const formData = new FormData();
      formData.append('file', file);

      if (onProgress) {
        xhr.upload.addEventListener('progress', (e) => {
          if (e.lengthComputable) {
            onProgress(Math.round((e.loaded / e.total) * 100));
          }
        });
      }

      xhr.addEventListener('load', () => {
        if (xhr.status === 200) {
          resolve(JSON.parse(xhr.responseText) as UploadResult);
        } else if (xhr.status === 401) {
          reject(new Error('Unauthorized'));
        } else if (xhr.status === 413) {
          try {
            const data = JSON.parse(xhr.responseText);
            reject(new Error(data.detail || 'Файл слишком тяжёлый'));
          } catch {
            reject(new Error('Файл слишком тяжёлый'));
          }
        } else if (xhr.status === 429) {
          try {
            const data = JSON.parse(xhr.responseText);
            reject(new Error(data.detail || 'Слишком много файлов'));
          } catch {
            reject(new Error('Слишком много файлов'));
          }
        } else {
          reject(new Error(`HTTP ${xhr.status}`));
        }
      });

      xhr.addEventListener('error', () => reject(new Error('Network error')));

      xhr.open('POST', `${this.baseUrl}/upload?session=${encodeURIComponent(this.session ?? '')}`);
      xhr.send(formData);
    });
  }

  fileUrl(dir: 'inbox' | 'output', filename: string): string {
    return `${this.baseUrl}/files/${dir}/${encodeURIComponent(filename)}?session=${encodeURIComponent(this.session ?? '')}`;
  }

  // History
  async fetchHistory(limit = 50, scope: 'chat' | 'tech' = 'chat'): Promise<HistoryResult> {
    if (this.mock) {
      await this._delay(200);
      return FIXTURES.history as HistoryResult;
    }
    const res = await fetch(
      `${this.baseUrl}/history?session=${encodeURIComponent(this.session ?? '')}&limit=${limit}&scope=${scope}`
    );
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    return (await res.json()) as HistoryResult;
  }

  // WS lifecycle
  connect(): Promise<void> {
    if (this._connected || this._connecting) return Promise.resolve();
    this._connecting = true;
    this._manualDisconnect = false;

    return new Promise((resolve, reject) => {
      if (this.mock) {
        this._connecting = false;
        this._connected = true;
        this._startMockFlow();
        resolve();
        return;
      }

      const url = `${this.baseUrl.replace(/^http/, 'ws')}/ws?session=${encodeURIComponent(this.session ?? '')}`;
      try {
        this.ws = new WebSocket(url);
      } catch (e) {
        this._connecting = false;
        reject(e);
        return;
      }

      this.ws.onopen = () => {
        this._connected = true;
        this._connecting = false;
        this.reconnectAttempts = 0;
        this._startPing();
        resolve();
      };

      this.ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as ServerMessage;
          this._emit(msg);
        } catch {
          // ignore malformed
        }
      };

      this.ws.onclose = (event) => {
        this._cleanup();
        if (!this._manualDisconnect && event.code !== 4001) {
          this._scheduleReconnect();
        }
        if (event.code === 4001) {
          this._emit({ type: 'auth_required', bot: '' });
        }
      };

      this.ws.onerror = () => {
        this._connecting = false;
        reject(new Error('WebSocket error'));
      };
    });
  }

  disconnect(): void {
    this._manualDisconnect = true;
    this._cleanup();
    if (this.ws) {
      try {
        this.ws.close();
      } catch {
        // ignore
      }
      this.ws = null;
    }
  }

  /** Принудительное немедленное переподключение (кнопка в UI).
   * Отменяет отложенный реконнект-таймер, сбрасывает backoff и сразу
   * подключается заново. Слушатели (on/onTech) переживают реконнект —
   * их перерегистрировать не нужно. */
  reconnect(): Promise<void> {
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.reconnectAttempts = 0;
    this._manualDisconnect = false;
    if (this.ws) {
      try {
        this.ws.close();
      } catch {
        // ignore
      }
      this.ws = null;
    }
    this._cleanup();
    return this.connect();
  }

  private _cleanup(): void {
    this._connected = false;
    this._connecting = false;
    if (this.pingInterval) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  private _scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    const delay = Math.min(1000 * 2 ** this.reconnectAttempts, this.maxReconnectDelay);
    this.reconnectAttempts++;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      this.connect().catch(() => {
        // will retry again via onclose
      });
    }, delay);
  }

  private _startPing(): void {
    this.pingInterval = setInterval(() => {
      this._send({ type: 'ping' });
    }, 30000);
  }

  private _send(msg: ClientMessage): void {
    if (this.mock) return;
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  // Sending
  sendMessage(text: string, attachments?: string | string[], mode?: 'chat' | 'tech'): void {
    const payload: Record<string, unknown> = { content: text };
    if (attachments) {
      payload.attachments = Array.isArray(attachments) ? attachments : [attachments];
    }
    if (mode === 'tech') {
      payload.mode = 'tech';
    }
    this._send(payload as ClientMessage);
    if (this.mock) {
      this._mockReply(text);
    }
  }

  sendCommand(cmd: string): void {
    this._send({ type: 'command', cmd });
    if (this.mock) {
      this._mockCommand(cmd);
    }
  }

  /** Сохранить анкету (профиль, заполняемый пользователем). */
  saveProfile(form: ProfileForm): void {
    this._send({ type: 'profile_save', form });
  }

  /**
   * Sends a command and waits for the first message matching one of `expectedTypes`.
   *
   * INVARIANT: Only one modal / caller should use `sendCommandAwait` at a time
   * for overlapping `expectedTypes`. The awaiter queue is first-come-first-served;
   * if two awaiters register for the same type, the first one will receive the
   * next message regardless of which command triggered it. This is acceptable
   * for modal dialogs (which are mutually exclusive) but will cross-wire if
   * non-modal UI also starts awaiting.
   */
  sendCommandAwait<T extends ServerMessage['type']>(
    cmd: string,
    expectedTypes: T[],
    timeoutMs = 10000
  ): Promise<Extract<ServerMessage, { type: T }>> {
    return new Promise((resolve, reject) => {
      let timer: ReturnType<typeof setTimeout> | null = null;

      const entry = {
        types: expectedTypes as ServerMessage['type'][],
        resolve: (msg: ServerMessage) => {
          if (timer) clearTimeout(timer);
          this._removeAwaiter(entry);
          resolve(msg as Extract<ServerMessage, { type: T }>);
        },
      };

      const cleanup = () => {
        if (timer) clearTimeout(timer);
        this._removeAwaiter(entry);
      };

      timer = setTimeout(() => {
        cleanup();
        reject(new Error('Timeout'));
      }, timeoutMs);

      this.awaiters.push(entry);
      this.sendCommand(cmd);
    });
  }

  private _removeAwaiter(entry: { types: ServerMessage['type'][]; resolve: (msg: ServerMessage) => void }): void {
    const idx = this.awaiters.indexOf(entry);
    if (idx !== -1) this.awaiters.splice(idx, 1);
  }

  // Events
  on<T extends ServerMessage['type']>(
    type: T,
    handler: MessageHandler<T>
  ): () => void {
    const set = this.listeners.get(type) || new Set();
    const wrapped = (msg: ServerMessage) => handler(msg as Extract<ServerMessage, { type: T }>);
    set.add(wrapped);
    this.listeners.set(type, set);
    return () => set.delete(wrapped);
  }

  private _emit(msg: ServerMessage): void {
    // Технический канал — owner-only поток: ритуалы, system, approval_request.
    // Не попадает в общий чат и не разбирается awaiter'ами.
    const raw = msg as unknown as { channel?: string };
    if (raw.channel === 'tech') {
      this.techListeners.forEach((h) => h(msg as unknown as TechEvent));
      return;
    }
    // First, try to deliver to awaiters (first-come-first-served).
    // If an awaiter is waiting for this message type, it consumes the message
    // and public listeners will NOT receive it. This prevents modal responses
    // from being duplicated into the chat stream.
    const idx = this.awaiters.findIndex((a) => a.types.includes(msg.type));
    if (idx !== -1) {
      const awaiter = this.awaiters[idx];
      this.awaiters.splice(idx, 1);
      awaiter.resolve(msg);
      return;
    }

    // If no awaiter, deliver to public listeners
    const set = this.listeners.get(msg.type);
    if (set) set.forEach((h) => h(msg));
  }

  // ── Tech channel ───────────────────────────────────────────────
  onTech(handler: (ev: TechEvent) => void): () => void {
    this.techListeners.add(handler);
    return () => this.techListeners.delete(handler);
  }

  async listOwnerInbox(sinceId = 0, unreadOnly = false): Promise<OwnerInboxItem[]> {
    if (this.mock) return [];
    const params = new URLSearchParams({
      session: this.session ?? '',
      since_id: String(sinceId),
      limit: '200',
      unread: unreadOnly ? '1' : '0',
    });
    const res = await fetch(`${this.baseUrl}/m/owner_inbox?${params}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = (await res.json()) as { items: OwnerInboxItem[] };
    return data.items;
  }

  async markInboxRead(id: number): Promise<boolean> {
    if (this.mock) return true;
    const res = await fetch(`${this.baseUrl}/m/owner_inbox/${id}/read`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session: this.session ?? '' }),
    });
    if (!res.ok) return false;
    const data = (await res.json()) as { ok: boolean };
    return !!data.ok;
  }

  async inboxAction(id: number, action: string): Promise<{ ok: boolean; applied?: boolean; target?: string }> {
    if (this.mock) return { ok: true };
    const res = await fetch(`${this.baseUrl}/m/owner_inbox/${id}/action`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session: this.session ?? '', action }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return (await res.json()) as { ok: boolean; applied?: boolean; target?: string };
  }

  get connected(): boolean {
    return this._connected;
  }

  get connecting(): boolean {
    return this._connecting;
  }

  // Mock helpers
  private _delay(ms: number): Promise<void> {
    return new Promise((r) => setTimeout(r, ms));
  }

  private _startMockFlow(): void {
    setTimeout(() => {
      this._emit({ ...(FIXTURES.ws_ready as object) } as ServerMessage);
    }, 300);
  }

  private async _mockReply(text: string): Promise<void> {
    this._emit({ ...(FIXTURES.ws_thinking as object) } as ServerMessage);
    await this._delay(800 + Math.random() * 1000);
    if (text.toLowerCase().includes('привет')) {
      this._emit({ ...(FIXTURES.ws_message_simple as object) } as ServerMessage);
    } else {
      this._emit({
        type: 'message',
        content: `Ты написал: "${text}". Это тестовый ответ из mock-режима.`,
      } as unknown as ServerMessage);
    }
  }

  private async _mockCommand(cmd: string): Promise<void> {
    await this._delay(300);
    if (cmd === 'clear') {
      this._emit({ ...(FIXTURES.ws_system_history_cleared as object) } as ServerMessage);
    } else if (cmd === 'whoami') {
      this._emit({ ...(FIXTURES.ws_system_whoami as object) } as ServerMessage);
    } else {
      this._emit({
        type: 'system',
        content: `Команда "${cmd}" получена (mock).`,
      } as unknown as ServerMessage);
    }
  }
}
