export interface TelegramAuthData {
  id: string;
  first_name: string;
  last_name?: string;
  username?: string;
  photo_url?: string;
  auth_date: string;
  hash: string;
}

export interface AuthResult {
  ok: boolean;
  session?: string;
  name?: string;
  is_new?: boolean;
  error?: string;
}

export interface HealthStatus {
  status: string;
  bot_alive: boolean;
  web_alive: boolean;
}

export interface HistoryResult {
  messages: Array<{ role: string; content: string }>;
}

export interface UploadResult {
  ok: boolean;
  filename: string;
  size: number;
}

export type ServerMessage =
  | { type: 'ready'; name: string }
  | { type: 'auth_required'; bot: string }
  | { type: 'pong' }
  | { type: 'thinking' }
  | { type: 'message'; content: string }
  | { type: 'system'; content: string }
  | { type: 'error'; content: string }
  | { type: 'files'; files: Array<{ name: string; dir: string; size: number }> }
  | { type: 'gdrive_auth_url'; url: string };

export type ClientMessage =
  | { type: 'ping' }
  | { type: 'command'; cmd: string }
  | { content: string };
