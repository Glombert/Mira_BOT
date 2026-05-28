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
  | { type: 'ready'; name: string; is_owner?: boolean; is_approved?: boolean; gdrive_authorized?: boolean; gdrive_email?: string | null; permissions?: string[]; counts?: SidebarCounts }
  | { type: 'approval_request'; user_id: string; name: string; source: string }
  | { type: 'permissions_update'; is_owner?: boolean; is_approved?: boolean; gdrive_authorized?: boolean; gdrive_email?: string | null; permissions?: string[] }
  | { type: 'auth_required'; bot: string }
  | { type: 'pong' }
  | { type: 'thinking' }
  | { type: 'message'; content: string; attachments?: Array<{ name: string; size: number }>; cards?: MessageCard[] }
  | { type: 'system'; content: string }
  | { type: 'error'; content: string }
  | { type: 'files'; files: Array<{ name: string; dir: string; size: number }> }
  | { type: 'gdrive_auth_url'; url: string }
  | { type: 'users_list'; users: UserEntry[] }
  | { type: 'learned'; insight: string }
  | { type: 'profile_data'; profile: ProfileData }
  | { type: 'profile_saved' };

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
  | { content: string; attachment?: string; attachments?: string[] };
