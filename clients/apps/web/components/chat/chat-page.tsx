'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { MiraClient } from '@mira/shared';
import type { ServerMessage, SidebarCounts, OwnerInboxItem, TechEvent } from '@mira/shared';
import { webSessionStorage } from '@/lib/session-storage';
import { IS_TAURI } from '@/lib/runtime';
import { TelegramLogin } from '@/components/auth/telegram-login';
import { ChatHeader } from './chat-header';
import { ChatInput } from './chat-input';
import { ChatMessageBubble, type ChatMessageItem } from './chat-message';
import { loadCachedHistory, saveCachedHistory, clearCachedHistory } from '@/lib/history-cache';
import { WhoamiModal } from '@/components/ui/whoami-modal';
import { RemindersModal } from '@/components/ui/reminders-modal';
import { DriveModal } from '@/components/ui/drive-modal';
import { ProfileModal } from '@/components/ui/profile-modal';
import { CreateReminderModal } from '@/components/ui/create-reminder-modal';
import { WebDrawer } from './web-drawer';
import { TechInbox, type TechFeedEntry } from './tech-inbox';
import { ProfileScreen } from '@/components/screens/profile-screen';
import { FilesScreen } from '@/components/screens/files-screen';
import { RemindersScreen } from '@/components/screens/reminders-screen';
import { UsersScreen } from '@/components/screens/users-screen';
import { TasksScreen } from '@/components/screens/tasks-screen';
import { MetricsScreen } from '@/components/screens/metrics-screen';
import { RitualsScreen } from '@/components/screens/rituals-screen';
import { BackupsScreen } from '@/components/screens/backups-screen';

function generateId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function buildTechFeed(
  inbox: OwnerInboxItem[],
  msgs: Array<{ role: 'user' | 'assistant'; content: string; ts: number }>,
  thinking: boolean,
  error: string | null,
  thought: string | null,
): TechFeedEntry[] {
  const entries: TechFeedEntry[] = [];
  for (const it of inbox) {
    const t = Date.parse(it.ts);
    entries.push({ kind: 'inbox', ts: Number.isFinite(t) ? t : Date.now(), item: it });
  }
  for (const m of msgs) {
    entries.push({ kind: 'msg', ts: m.ts, role: m.role, content: m.content });
  }
  entries.sort((a, b) => a.ts - b.ts);
  if (thought) {
    entries.push({ kind: 'thought', ts: Date.now(), content: thought });
  } else if (thinking) {
    entries.push({ kind: 'thinking', ts: Date.now() });
  }
  if (error) {
    entries.push({ kind: 'error', ts: Date.now(), content: error });
  }
  return entries;
}

function TabSwitcher({
  mode,
  setMode,
  unreadTech,
}: {
  mode: 'chat' | 'tech';
  setMode: (m: 'chat' | 'tech') => void;
  unreadTech: number;
}) {
  const baseBtn =
    'flex-1 py-2 text-sm font-medium border-b-2 transition-colors';
  const active = 'border-gold-soft text-text-primary';
  const idle = 'border-transparent text-text-muted hover:text-text-secondary';
  return (
    <div className="flex border-b border-border-divider bg-bg-base">
      <button className={`${baseBtn} ${mode === 'chat' ? active : idle}`} onClick={() => setMode('chat')}>
        Чат
      </button>
      <button className={`${baseBtn} ${mode === 'tech' ? active : idle} relative`} onClick={() => setMode('tech')}>
        Техника
        {unreadTech > 0 && (
          <span className="absolute top-1 right-1/3 -translate-x-1/2 px-1.5 py-0.5 text-[10px] rounded-full bg-rose/80 text-bg-base font-semibold">
            {unreadTech > 99 ? '99+' : unreadTech}
          </span>
        )}
      </button>
    </div>
  );
}

const BOT_USERNAME = process.env.NEXT_PUBLIC_BOT_USERNAME || 'MiraTestBot';
const BASE_URL = process.env.NEXT_PUBLIC_MIRA_URL || 'http://localhost:8000';
const IS_MOCK = process.env.NEXT_PUBLIC_MIRA_MOCK === 'true';

export function ChatPage() {
  const [client, setClient] = useState<MiraClient | null>(null);
  const [session, setSession] = useState<string | null>(null);
  const [userName, setUserName] = useState<string>('');
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [connectionStatus, setConnectionStatus] = useState<'online' | 'reconnecting' | 'offline'>('offline');
  const [showAuth, setShowAuth] = useState(false);
  const [whoamiContent, setWhoamiContent] = useState<string | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [counts, setCounts] = useState<SidebarCounts>({});
  const [remindersOpen, setRemindersOpen] = useState(false);
  const [driveOpen, setDriveOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [profileOnboarding, setProfileOnboarding] = useState(false);
  const onboardCheckedRef = useRef(false);
  const [isDragging, setIsDragging] = useState(false);
  const [pendingAttachment, setPendingAttachment] = useState<{ name: string; size: number } | null>(null);
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const unsubscribersRef = useRef<(() => void)[]>([]);
  const pendingWhoamiRef = useRef(false);
  const historyLoadedRef = useRef(false);
  const dragCounterRef = useRef(0);
  const pendingFilesRef = useRef<File[]>([]);
  const uploadResultsRef = useRef<Array<{ filename: string; size: number }>>([]);
  const [autoScroll, setAutoScroll] = useState(true);
  const [permissions, setPermissions] = useState({ is_owner: false, is_approved: true, gdrive_authorized: false, gdrive_email: null as string | null, permissions: [] as string[] });
  const [mode, setMode] = useState<'chat' | 'tech'>('chat');
  const [screen, setScreen] = useState<string>('chat');
  const [inbox, setInbox] = useState<OwnerInboxItem[]>([]);
  const [techMessages, setTechMessages] = useState<Array<{ role: 'user' | 'assistant'; content: string; ts: number }>>([]);
  const [techThinking, setTechThinking] = useState(false);
  const [techThought, setTechThought] = useState<string | null>(null);
  const [techError, setTechError] = useState<string | null>(null);
  const [unreadTech, setUnreadTech] = useState(0);
  const inboxLoadedRef = useRef(false);

  const clientRef = useRef<MiraClient | undefined>(undefined);
  useEffect(() => {
    (async () => {
      const storage = IS_TAURI
        ? (await import('@/lib/tauri-session-storage')).tauriSessionStorage
        : webSessionStorage;
      const c = new MiraClient({ baseUrl: BASE_URL, mock: IS_MOCK, sessionStorage: storage });
      clientRef.current = c;
      setClient(c);

      const stored = await c.loadSession();
      if (stored) {
        setSession(stored);
        connectClient(c);
      } else {
        setShowAuth(true);
      }
    })();

    return () => {
      clientRef.current?.disconnect();
      unsubscribersRef.current.forEach((u) => u());
      unsubscribersRef.current = [];
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const addMessage = useCallback((msg: ChatMessageItem) => {
    setMessages((prev) => {
      if (msg.type === 'message' || msg.type === 'error') {
        const filtered = prev.filter((m) => m.type !== 'thinking' && m.type !== 'thought');
        return [...filtered, msg];
      }
      return [...prev, msg];
    });
  }, []);

  const connectClient = useCallback((c: MiraClient) => {
    unsubscribersRef.current.forEach((u) => u());
    unsubscribersRef.current = [];

    setConnectionStatus('reconnecting');

    const unsubReady = c.on('ready', (msg) => {
      setConnectionStatus('online');
      setUserName(msg.name);
      setShowAuth(false);
      setPermissions({
        is_owner: msg.is_owner ?? false,
        is_approved: msg.is_approved ?? true,
        gdrive_authorized: msg.gdrive_authorized ?? false,
        gdrive_email: msg.gdrive_email ?? null,
        permissions: msg.permissions ?? [],
      });
      setCounts(msg.counts ?? {});
      // Owner: подтянуть техническую ленту + историю tech-чата
      if (msg.is_owner && !inboxLoadedRef.current) {
        inboxLoadedRef.current = true;
        c.listOwnerInbox(0).then((items) => {
          setInbox(items);
          setUnreadTech(items.filter((it) => !it.is_read).length);
        }).catch(() => {});
        c.fetchHistory(80, 'tech').then((h) => {
          const msgs = h.messages
            .filter((m) => m.role === 'user' || m.role === 'assistant')
            .map((m) => ({
              role: m.role as 'user' | 'assistant',
              content: m.content,
              ts: typeof m.ts === 'number' && m.ts > 0 ? Math.round(m.ts * 1000) : Date.now(),
            }));
          if (msgs.length) setTechMessages(msgs);
        }).catch(() => {});
      }
      // Анкета после одобрения: одобренным (не владельцу), кто ещё не заполнил
      if (msg.is_approved && !msg.is_owner && !onboardCheckedRef.current) {
        onboardCheckedRef.current = true;
        c.sendCommandAwait('profile_data', ['profile_data'], 12000)
          .then((m) => {
            if ('profile' in m && !m.profile.onboarded) {
              setProfileOnboarding(true);
              setProfileOpen(true);
            }
          })
          .catch(() => {});
      }
      if (!historyLoadedRef.current) {
        historyLoadedRef.current = true;
        c.fetchHistory(50).then((hist) => {
          if (hist.messages.length > 0) {
            const historyMsgs: ChatMessageItem[] = hist.messages.map((m) => ({
              id: generateId(),
              type: m.role === 'user' ? 'user' : 'message',
              content: m.content,
              timestamp: typeof m.ts === 'number' && m.ts > 0 ? Math.round(m.ts * 1000) : 0,
            }));
            setMessages(historyMsgs);
          }
        }).catch(() => {});
      }
    });

    const unsubAuthRequired = c.on('auth_required', () => {
      setConnectionStatus('offline');
      setShowAuth(true);
      historyLoadedRef.current = false;
      c.clearSession().catch(() => {});
    });

    const unsubThinking = c.on('thinking', () => {
      addMessage({ id: generateId(), type: 'thinking', timestamp: Date.now() });
    });

    const unsubThought = c.on('thought', (msg) => {
      // Заменяем последний thinking-индикатор на 💭-облачко с действием.
      setMessages((prev) => {
        const idx = [...prev].reverse().findIndex((m) => m.type === 'thinking' || m.type === 'thought');
        if (idx === -1) {
          return [...prev, { id: generateId(), type: 'thought' as const, content: msg.content, timestamp: Date.now() }];
        }
        const realIdx = prev.length - 1 - idx;
        const next = [...prev];
        next[realIdx] = { ...next[realIdx], type: 'thought' as const, content: msg.content };
        return next;
      });
    });

    const unsubMessage = c.on('message', (msg) => {
      addMessage({ id: generateId(), type: 'message', content: msg.content, messageAttachments: msg.attachments, cards: msg.cards, timestamp: Date.now() });
    });

    const unsubApproval = c.on('approval_request', (msg) => {
      addMessage({ id: generateId(), type: 'approval_request', approval: { user_id: msg.user_id, name: msg.name, source: msg.source }, timestamp: Date.now() });
    });

    const unsubPermissionsUpdate = c.on('permissions_update', (msg) => {
      setPermissions((prev) => ({ ...prev, is_owner: msg.is_owner ?? prev.is_owner, is_approved: msg.is_approved ?? prev.is_approved, gdrive_authorized: msg.gdrive_authorized ?? prev.gdrive_authorized, gdrive_email: msg.gdrive_email ?? prev.gdrive_email, permissions: msg.permissions ?? prev.permissions }));
    });

    const unsubSystem = c.on('system', (msg) => {
      if (pendingWhoamiRef.current) {
        setWhoamiContent(msg.content);
        pendingWhoamiRef.current = false;
        return;
      }
      const oauthMatch = msg.content.match(/https:\/\/accounts\.google\.com\/o\/oauth2\/[^\s]+/);
      if (oauthMatch) {
        window.open(oauthMatch[0], '_blank');
        return;
      }
      addMessage({ id: generateId(), type: 'system', content: msg.content, timestamp: Date.now() });
    });

    const unsubError = c.on('error', (msg) => {
      addMessage({ id: generateId(), type: 'error', content: msg.content, timestamp: Date.now() });
    });

    const unsubPong = c.on('pong', () => {});

    const unsubFiles = c.on('files', (msg) => {
      addMessage({ id: generateId(), type: 'files', files: msg.files, timestamp: Date.now() });
    });

    const unsubGdrive = c.on('gdrive_auth_url', (msg) => {
      addMessage({ id: generateId(), type: 'gdrive_auth_url', url: msg.url, timestamp: Date.now() });
    });

    const unsubTech = c.onTech((ev: TechEvent) => {
      if (ev.type === 'inbox_update') {
        if (ev.id != null) {
          setInbox((prev) => prev.map((it) =>
            it.id === ev.id ? { ...it, is_read: true, action: ev.action ?? it.action } : it
          ));
        }
        return;
      }
      if (ev.type === 'thinking') {
        setTechThinking(true);
        setTechThought(null);
        return;
      }
      if (ev.type === 'thought') {
        setTechThinking(true);
        setTechThought(ev.content ?? '');
        return;
      }
      if (ev.type === 'message') {
        setTechThinking(false);
        setTechThought(null);
        setTechError(null);
        setTechMessages((prev) => [...prev, {
          role: 'assistant',
          content: ev.content ?? ev.body ?? '',
          ts: typeof ev.ts === 'number' ? ev.ts * 1000 : Date.now(),
        }]);
        return;
      }
      if (ev.type === 'error') {
        setTechThinking(false);
        setTechError(ev.content ?? ev.body ?? 'Ошибка');
        return;
      }
      // ritual/system/approval_request — события inbox
      const item: OwnerInboxItem = {
        id: ev.id ?? Date.now(),
        ts: typeof ev.ts === 'string' ? ev.ts : new Date().toISOString(),
        type: ev.type,
        importance: ev.importance ?? 'NONE',
        title: ev.title ?? '',
        body: ev.body ?? '',
        payload: ev.user_id || ev.buttons
          ? { user_id: ev.user_id, name: ev.name, source: ev.source, buttons: ev.buttons }
          : null,
        is_read: false,
        action: null,
      };
      setInbox((prev) => {
        if (prev.some((p) => p.id === item.id && item.id < 1e12)) return prev;
        return [...prev, item];
      });
      setUnreadTech((n) => n + 1);
    });

    unsubscribersRef.current = [
      unsubReady, unsubAuthRequired, unsubThinking, unsubThought, unsubMessage,
      unsubApproval, unsubPermissionsUpdate, unsubSystem, unsubError,
      unsubPong, unsubFiles, unsubGdrive, unsubTech,
    ];

    c.connect().catch(() => setConnectionStatus('offline'));
  }, [addMessage]);

  const handleAuth = useCallback(
    async (user: { id: string; first_name: string; last_name?: string; username?: string; photo_url?: string; auth_date: string; hash: string }) => {
      if (!client) return;
      const result = await client.authenticate(user);
      if (result.ok && result.session) {
        await client.setSession(result.session);
        setSession(result.session);
        setUserName(result.name || '');
        connectClient(client);
      } else {
        addMessage({ id: generateId(), type: 'error', content: result.error || 'Ошибка авторизации', timestamp: Date.now() });
      }
    },
    [client, connectClient, addMessage]
  );

  const handleReconnect = useCallback(() => {
    const c = clientRef.current;
    if (!c) return;
    setConnectionStatus('reconnecting');
    c.reconnect().catch(() => setConnectionStatus('offline'));
  }, []);

  // Авто-реконнект: вкладка снова видима или вернулась сеть. Пока вкладка в фоне,
  // браузер тормозит пинги, и сервер рвёт молчащую WS-линию через таймаут —
  // возвращаемся и сразу переподключаемся, не дожидаясь backoff.
  useEffect(() => {
    const resume = () => {
      const c = clientRef.current;
      if (c && session && !c.connected) {
        setConnectionStatus('reconnecting');
        c.reconnect().catch(() => setConnectionStatus('offline'));
      }
    };
    const onVisible = () => { if (document.visibilityState === 'visible') resume(); };
    window.addEventListener('online', resume);
    document.addEventListener('visibilitychange', onVisible);
    return () => {
      window.removeEventListener('online', resume);
      document.removeEventListener('visibilitychange', onVisible);
    };
  }, [session]);

  // Офлайн-кэш истории: показываем мгновенно при открытии (до ответа сервера).
  useEffect(() => {
    const cached = loadCachedHistory();
    if (cached.length) setMessages((prev) => (prev.length ? prev : cached));
  }, []);
  useEffect(() => {
    if (messages.length) saveCachedHistory(messages);
  }, [messages]);

  const handleAuthRef = useRef(handleAuth);
  handleAuthRef.current = handleAuth;

  const handleSend = useCallback(
    (text: string) => {
      if (!client || !session) return;
      const trimmed = text.trim();
      const atts = uploadResultsRef.current;

      if (!trimmed && atts.length === 0) return;

      let displayContent = trimmed;
      const names = atts.map((a) => a.filename);

      if (atts.length > 0) {
        const attLines = atts.map((a) => '📎 ' + a.filename).join('\n');
        displayContent = trimmed ? trimmed + '\n\n' + attLines : attLines;
      }

      addMessage({ id: generateId(), type: 'user', content: displayContent, timestamp: Date.now() });
      client.sendMessage(trimmed, names.length > 0 ? names : undefined);
      setAutoScroll(true);

      // clear
      uploadResultsRef.current = [];
      pendingFilesRef.current = [];
      setPendingAttachment(null);
    },
    [client, session, addMessage]
  );

  const handleClear = useCallback(() => {
    if (!client) return;
    if (!window.confirm('Точно очистить историю? Действие необратимо.')) return;
    client.sendCommand('clear');
    setMessages([]);
    clearCachedHistory();
  }, [client]);

  const handleWhoami = useCallback(() => {
    if (!client) return;
    pendingWhoamiRef.current = true;
    client.sendCommand('whoami');
  }, [client]);

  const handleOpenPalette = useCallback(() => setPaletteOpen(true), []);
  const handleOpenReminders = useCallback(() => setRemindersOpen(true), []);
  const handleOpenDrive = useCallback(() => setDriveOpen(true), []);

  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const showToast = useCallback((t: string) => {
    setToast(t.slice(0, 160));
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 2800);
  }, []);

  // Действие из меню: подтверждение тостом, не в чат. image/gdrive_login → в чат.
  const handlePaletteRun = useCallback(
    (cmd: string) => {
      if (!client) return;
      const base = cmd.split(' ')[0];
      if (base === 'clear') { setMessages([]); clearCachedHistory(); }
      if (base === 'image' || base === 'gdrive_login') {
        client.sendCommand(cmd);
        return;
      }
      client
        .sendCommandAwait(cmd, ['system', 'message'])
        .then((m) => showToast('content' in m ? m.content : 'Готово'))
        .catch(() => {});
    },
    [client, showToast]
  );

  const handleFetchInfo = useCallback((cmd: string): Promise<string> => {
    if (!client) return Promise.resolve('Нет соединения');
    return client
      .sendCommandAwait(cmd, ['system', 'message'])
      .then((m) => ('content' in m ? m.content : '—'))
      .catch(() => 'Не удалось получить данные');
  }, [client]);

  const handleFetchUsers = useCallback(() => {
    if (!client) return Promise.resolve([]);
    return client
      .sendCommandAwait('users_data', ['users_list'])
      .then((m) => m.users)
      .catch(() => []);
  }, [client]);

  const handleApprove = useCallback(
    (userId: string) => {
      if (!client) return;
      client.sendCommand('approve ' + userId);
    },
    [client]
  );

  const handleBlock = useCallback(
    (userId: string) => {
      if (!client) return;
      client.sendCommand('block ' + userId);
    },
    [client]
  );

  const handleInboxLocalUpdate = useCallback(
    (id: number, patch: Partial<OwnerInboxItem>) => {
      setInbox((prev) => prev.map((it) => (it.id === id ? { ...it, ...patch } : it)));
    },
    []
  );

  const handleSendTech = useCallback((text: string) => {
    if (!client) return;
    setTechMessages((prev) => [...prev, { role: 'user', content: text, ts: Date.now() }]);
    setTechError(null);
    setTechThought(null);
    setTechThinking(true);
    client.sendMessage(text, undefined, 'tech');
  }, [client]);

  // При переключении на «Техника» — отметить непрочитанные прочитанными
  useEffect(() => {
    if (mode !== 'tech' || !client) return;
    const unread = inbox.filter((it) => !it.is_read);
    if (unread.length === 0) return;
    unread.forEach((it) => {
      client.markInboxRead(it.id).catch(() => {});
    });
    setInbox((prev) => prev.map((it) => (it.is_read ? it : { ...it, is_read: true })));
    setUnreadTech(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  // Global keybind Cmd+K / Ctrl+K
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const doUpload = useCallback(
    async (files: File[]) => {
      if (!client || !session) return;
      const current = uploadResultsRef.current.length;
      if (current + files.length > 5) {
        addMessage({ id: generateId(), type: 'system', content: 'Максимум 5 файлов за раз', timestamp: Date.now() });
        return;
      }
      pendingFilesRef.current = [...pendingFilesRef.current, ...files];
      setUploadProgress(0);
      const newResults: Array<{ filename: string; size: number }> = [];
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        try {
          const result = await client.uploadFile(file, (pct) => setUploadProgress(Math.round(((i + pct / 100) / files.length) * 100)));
          newResults.push({ filename: result.filename, size: result.size });
        } catch (err) {
          const msg = err instanceof Error ? err.message : 'Ошибка загрузки';
          if (msg === 'Unauthorized') {
            setConnectionStatus('offline');
            setShowAuth(true);
            uploadResultsRef.current = [];
            pendingFilesRef.current = [];
            setPendingAttachment(null);
            setUploadProgress(null);
            return;
          }
          addMessage({ id: generateId(), type: 'error', content: `${file.name}: ${msg}`, timestamp: Date.now() });
        }
      }
      uploadResultsRef.current = [...uploadResultsRef.current, ...newResults];
      if (newResults.length > 0) {
        setPendingAttachment({ name: newResults.map((r) => r.filename).join(', '), size: newResults.reduce((s, r) => s + r.size, 0) });
      }
      setUploadProgress(null);
    },
    [client, session, addMessage]
  );

  const handleFileSelect = useCallback(
    (files: File[]) => {
      doUpload(files);
    },
    [doUpload]
  );

  const handleClearAttachment = useCallback(() => {
    pendingFilesRef.current = [];
    uploadResultsRef.current = [];
    setPendingAttachment(null);
  }, []);

  // Drag & drop
  const handleDragEnter = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    dragCounterRef.current++;
    setIsDragging(true);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    dragCounterRef.current--;
    if (dragCounterRef.current <= 0) {
      dragCounterRef.current = 0;
      setIsDragging(false);
    }
  }, []);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      dragCounterRef.current = 0;
      setIsDragging(false);
      const files = Array.from(e.dataTransfer.files || []);
      if (files.length > 0) doUpload(files);
    },
    [doUpload]
  );

  // Deep-link auth listener (desktop only)
  useEffect(() => {
    if (!IS_TAURI || !client) return;
    let unlisten: (() => void) | undefined;
    (async () => {
      const { onOpenUrl } = await import('@tauri-apps/plugin-deep-link');
      unlisten = await onOpenUrl((urls) => {
        for (const url of urls) {
          const parsed = new URL(url);
          const isAuth = parsed.pathname === '/auth' || parsed.host === 'auth';
          if (!isAuth) continue;
          const id = parsed.searchParams.get('id');
          const first_name = parsed.searchParams.get('first_name') || '';
          const hash = parsed.searchParams.get('hash');
          const auth_date = parsed.searchParams.get('auth_date');
          if (!id || !hash || !auth_date) continue;
          handleAuthRef.current({
            id,
            first_name,
            last_name: parsed.searchParams.get('last_name') || undefined,
            username: parsed.searchParams.get('username') || undefined,
            photo_url: parsed.searchParams.get('photo_url') || undefined,
            auth_date,
            hash,
          });
        }
      });
    })();
    return () => {
      if (unlisten) unlisten();
    };
  }, [client]);

  // Auto scroll
  useEffect(() => {
    if (autoScroll && messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, autoScroll]);

  const handleScroll = useCallback(() => {
    if (!containerRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current;
    const nearBottom = scrollHeight - scrollTop - clientHeight < 80;
    setAutoScroll(nearBottom);
  }, []);

  return (
    <div className="flex flex-col h-[100dvh] bg-bg-base">
      <ChatHeader
        userName={userName}
        connectionStatus={connectionStatus}
        onClear={handleClear}
        onWhoami={handleWhoami}
        onOpenPalette={handleOpenPalette}
        onOpenReminders={handleOpenReminders}
        onOpenDrive={handleOpenDrive}
        onReconnect={handleReconnect}
      />

      {screen !== 'chat' && (
        <button
          onClick={() => setScreen('chat')}
          className="absolute top-3 left-3 z-30 h-9 w-9 flex items-center justify-center rounded-button border border-border-subtle bg-bg-deep/50 text-text-secondary hover:text-text-primary hover:border-border-strong transition-colors duration-fast"
          aria-label="Назад"
        >
          <svg width="18" height="18" viewBox="0 0 18 18" fill="none"><path d="M11 4 L6 9 L11 14" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/></svg>
        </button>
      )}

      {screen !== 'chat' ? (
        <>
          {screen === 'profile' && <ProfileScreen client={client} />}
          {screen === 'files' && <FilesScreen client={client} />}
          {screen === 'reminders' && <RemindersScreen client={client} />}
          {screen === 'users' && <UsersScreen client={client} />}
          {screen === 'tasks' && <TasksScreen client={client} />}
          {screen === 'metrics' && <MetricsScreen />}
          {screen === 'rituals' && <RitualsScreen />}
          {screen === 'backups' && <BackupsScreen />}
        </>
      ) : showAuth ? (
        <div className="flex-1 flex items-center justify-center px-4">
          <div className="w-full max-w-sm bg-bg-elevated rounded-card p-8 shadow-elevated">
            <TelegramLogin botUsername={BOT_USERNAME} mockEnabled={IS_MOCK} onAuth={handleAuth} />
          </div>
        </div>
      ) : permissions.is_owner && mode === 'tech' ? (
        <>
          <TabSwitcher mode={mode} setMode={setMode} unreadTech={unreadTech} />
          <TechInbox
            feed={buildTechFeed(inbox, techMessages, techThinking, techError, techThought)}
            client={client}
            onLocalUpdate={handleInboxLocalUpdate}
            onSend={handleSendTech}
            sending={techThinking}
          />
        </>
      ) : (
        <>
          {permissions.is_owner && (
            <TabSwitcher mode={mode} setMode={setMode} unreadTech={unreadTech} />
          )}
          <div
            ref={containerRef}
            onScroll={handleScroll}
            onDragEnter={handleDragEnter}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className="flex-1 overflow-y-auto px-4 py-4 space-y-3 scroll-smooth relative"
          >
            {isDragging && (
              <div className="absolute inset-0 z-20 flex items-center justify-center bg-bg-base/80 border-2 border-dashed border-accent rounded-lg m-2">
                <p className="text-accent text-lg font-medium">Брось файл сюда</p>
              </div>
            )}
            {uploadProgress !== null && (
              <div className="flex items-center justify-center gap-2 py-1">
                <span className="text-sm text-text-secondary">Загрузка {uploadProgress}%</span>
                <div className="w-32 h-1.5 bg-bg-overlay rounded-full overflow-hidden">
                  <div className="h-full bg-accent transition-all duration-200" style={{ width: `${uploadProgress}%` }} />
                </div>
              </div>
            )}
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center h-full gap-3 text-text-muted">
                <svg width="48" height="48" viewBox="0 0 28 28" fill="none">
                  <defs>
                    <linearGradient id="emptyStar" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse">
                      <stop stopColor="#f5bc7a" stopOpacity="0.3" />
                      <stop offset="1" stopColor="#f8cfa0" stopOpacity="0.2" />
                    </linearGradient>
                  </defs>
                  <path d="M14 2L16.5 11.5H26L18.5 17L21 26L14 21L7 26L9.5 17L2 11.5H11.5L14 2Z" fill="url(#emptyStar)" />
                </svg>
                <p className="text-sm text-text-secondary font-serif italic">Напиши что-нибудь, чтобы начать</p>
              </div>
            )}
            {messages.map((msg) => (
              <ChatMessageBubble key={msg.id} message={msg} getFileUrl={client?.fileUrl.bind(client)} onApprove={handleApprove} onBlock={handleBlock} />
            ))}
            <div ref={messagesEndRef} />
          </div>

          <div className="px-4 py-3 border-t border-border-subtle bg-bg-base">
            <ChatInput
              onSend={handleSend}
              onFileSelect={handleFileSelect}
              disabled={!session || connectionStatus === 'offline'}
              pendingAttachment={pendingAttachment}
              onClearAttachment={handleClearAttachment}
              uploading={uploadProgress !== null}
            />
          </div>
          {!autoScroll && (
            <button
              onClick={() => { messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' }); setAutoScroll(true); }}
              className="fixed right-6 bottom-24 z-10 w-10 h-10 rounded-full bg-bg-surface border border-border-strong flex items-center justify-center shadow-elevated hover:bg-bg-elevated transition-colors"
              aria-label="Вниз"
            >
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
                <path d="M6 9l6 6 6-6" stroke="#f5bc7a" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </button>
          )}
        </>
      )}

      {whoamiContent && <WhoamiModal content={whoamiContent} onClose={() => setWhoamiContent(null)} />}
      <WebDrawer open={paletteOpen} onClose={() => setPaletteOpen(false)} onRun={handlePaletteRun} onNavigate={(s) => setScreen(s)} permissions={permissions} userName={userName} onFetchInfo={handleFetchInfo} onFetchUsers={handleFetchUsers} counts={counts} onOpenProfile={() => { setPaletteOpen(false); setProfileOnboarding(false); setProfileOpen(true); }} />
      <ProfileModal open={profileOpen} onClose={() => setProfileOpen(false)} client={client} onboarding={profileOnboarding} />
      <RemindersModal open={remindersOpen} onClose={() => setRemindersOpen(false)} client={client} />
      <DriveModal open={driveOpen} onClose={() => setDriveOpen(false)} client={client} />
      {toast && (
        <div className="fixed bottom-24 left-1/2 -translate-x-1/2 z-[60] max-w-[80%] px-4 py-2 rounded-full bg-bg-surface border border-border-strong text-text-primary text-sm shadow-elevated text-center">
          {toast}
        </div>
      )}
    </div>
  );
}
