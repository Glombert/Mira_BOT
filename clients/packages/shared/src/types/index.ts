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
  messages: Array<{ role: string; content: string; ts?: number }>;
}

export interface UploadResult {
  ok: boolean;
  filename: string;
  size: number;
}

export type ServerMessage =
  | { type: 'ready'; name: string; is_owner?: boolean; is_approved?: boolean; gdrive_authorized?: boolean; gdrive_email?: string | null; permissions?: string[]; counts?: SidebarCounts }
  | { type: 'approval_request'; user_id: string; name: string; source: string }
  | { type: 'permissions_update'; is_owner?: boolean; is_approved?: boolean; gdrive_authorized?: boolean; gdrive_email?: string | null; permissions?: string[] }
  | { type: 'auth_required'; bot: string }
  | { type: 'pong' }
  | { type: 'thinking' }
  | { type: 'thought'; content: string }
  | { type: 'message'; content: string; attachments?: Array<{ name: string; size: number; dir?: string }>; cards?: MessageCard[] }
  | { type: 'system'; content: string }
  | { type: 'error'; content: string }
  | { type: 'files'; files: Array<{ name: string; dir: string; size: number }> }
  | { type: 'gdrive_auth_url'; url: string }
  | { type: 'users_list'; users: UserEntry[] }
  | { type: 'learned'; insight: string }
  | { type: 'profile_data'; profile: ProfileData }
  | { type: 'profile_saved' }
  | { type: 'metrics_data'; days: number; total_calls: number; total_tokens: number; cost_est: number; by_model: Array<{ model: string; calls: number; tokens: number; cost: number }>; by_day: Array<{ day: string; calls: number; cost: number }> }
  | { type: 'rituals_data'; rituals: Array<{ id: string; name: string; description: string; schedule: string; days: boolean[]; enabled: boolean; last_run?: string | null; next_run?: string | null }> }
  | { type: 'reminders_data'; reminders: Array<{ id: string; title: string; at: string; done: boolean; gcal: boolean; repeat?: string | null; mira_note?: string | null }> }
  | { type: 'tasks_data'; tasks: Array<{ id: string; message: string; at: string; status: string }> }
  | { type: 'backups_data'; schedule: string; storage: string; backups: Array<{ id: string; created_at: string; size: number; type: string; fact_count: number; note_count: number; is_latest: boolean }> };

/** Структурированный профиль для экрана «Профиль» (Aurora). */
export interface ProfileData {
  id: string;
  name: string;
  role: string;
  status: string;
  timezone: string;
  telegram: string;
  about_role: string;
  about_project: string;
  summary: string;
  gdrive_linked: boolean;
  gdrive_email: string;
  memory_facts: number;
  conversations: number;
  days_together: number;
  // анкета (пользователь заполняет сам)
  onboarded: boolean;
  addressing: string;
  address_form: string;
  manner: string[];
  origin: string;
  occupation: string;
  notes: string;
  manner_options: string[];
  filled_by_mira: string[];
}

/** Анкета — что пользователь сам сообщает о себе. */
export interface ProfileForm {
  addressing?: string;
  address_form?: string; // 'ты' | 'вы' | ''
  manner?: string[];
  origin?: string;
  occupation?: string;
  notes?: string;
  timezone?: string;
}

export interface UserEntry {
  id: string;
  name: string;
  status: string;
}

/** Запись в техническом канале владельца (owner_inbox). */
export interface OwnerInboxItem {
  id: number;
  ts: string;
  type: 'ritual' | 'system' | 'approval_request' | string;
  importance: 'NONE' | 'MINOR' | 'MAJOR' | 'CRITICAL' | string;
  title: string;
  body: string;
  payload: Record<string, unknown> | null;
  is_read: boolean;
  action: string | null;
}

/** WS-событие технического канала (channel === 'tech'). */
export interface TechEvent {
  channel: 'tech';
  type: 'ritual' | 'system' | 'approval_request' | 'inbox_update' | 'message' | 'thinking' | 'error' | string;
  id?: number;
  ts?: string | number;
  name?: string;
  user_id?: string;
  source?: string;
  importance?: string;
  title?: string;
  body?: string;
  content?: string;
  buttons?: Array<{ text: string; callback_data: string }>;
  action?: string;
}

/** Счётчики для бейджей в боковом меню (приходят в ready). */
export interface SidebarCounts {
  files?: number;
  reminders_today?: number;
  tasks?: number;
  users?: number;
  rituals?: number;
  evolutions?: number;
}

/** Структурированная карточка под сообщением Миры (Aurora attachment model). */
export interface MessageCard {
  kind: 'memory' | 'event' | 'backup';
  label: string;
  fact?: string;
  list?: string[] | null;
}

export type ClientMessage =
  | { type: 'ping' }
  | { type: 'command'; cmd: string }
  | { type: 'profile_save'; form: ProfileForm }
  | { content: string; attachment?: string; attachments?: string[]; mode?: 'chat' | 'tech' };
