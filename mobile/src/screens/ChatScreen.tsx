import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  View,
  StyleSheet,
  FlatList,
  Alert,
  StatusBar,
  KeyboardAvoidingView,
  Platform,
  Linking,
  TouchableOpacity,
  ToastAndroid,
  AppState,
} from 'react-native';
import Svg, { Path } from 'react-native-svg';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import { MiraClient } from '../api/mira-client';
import type { ChatMessageItem, UserPermissions, SidebarCounts } from '../types';
import { mobileSessionStorage } from '../utils/storage';
import { loadCachedHistory, saveCachedHistory, clearCachedHistory } from '../utils/historyCache';
import { checkForUpdate } from '../api/update';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { BASE_URL, IS_MOCK } from '../config';
import { colors, spacing } from '../theme';
import { AuroraTopbar } from '../components/AuroraTopbar';
import { AuroraMessage } from '../components/AuroraMessage';
import { AuroraComposer } from '../components/AuroraComposer';
import { AuroraWelcome } from '../components/AuroraWelcome';
import { AuroraSidebar } from '../components/AuroraSidebar';
import { CommandFormModal } from '../components/CommandFormModal';
import { ApprovalCard } from '../components/ApprovalCard';
import { WhoamiModal } from '../components/WhoamiModal';
import { RemindersModal } from '../components/RemindersModal';
import { DriveModal } from '../components/DriveModal';
import { ProfileModal } from '../components/ProfileModal';
import { FilesModal } from '../components/FilesModal';
import { MetricsModal } from '../components/MetricsModal';
import { RitualsModal } from '../components/RitualsModal';
import { TasksModal } from '../components/TasksModal';
import { BackupsModal } from '../components/BackupsModal';
import { ServerModal } from '../components/ServerModal';
import { VpnModal } from '../components/VpnModal';

function generateId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const DEFAULT_PERMISSIONS: UserPermissions = {
  is_owner: false,
  is_approved: true,
  gdrive_authorized: false,
  gdrive_email: null,
  permissions: ['chat'],
};

const ONBOARDING_CHIPS = [
  { label: 'Что ты умеешь?', action: 'send' as const, text: 'Что ты умеешь?' },
  { label: 'Привяжи Drive', action: 'cmd' as const, cmd: 'gdrive_login' },
  { label: 'Покажи мои файлы', action: 'cmd' as const, cmd: 'files' },
];

export function ChatScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<any>();
  const [techUnread, setTechUnread] = useState(0);
  const [client] = useState(() => new MiraClient({ baseUrl: BASE_URL, mock: IS_MOCK, sessionStorage: mobileSessionStorage }));
  const [session, setSession] = useState<string | null>(null);
  const [userName, setUserName] = useState('');
  const [mood, setMood] = useState('default');
  const [messages, setMessages] = useState<ChatMessageItem[]>([]);
  const [counts, setCounts] = useState<SidebarCounts>({});
  const [connectionStatus, setConnectionStatus] = useState<'online' | 'reconnecting' | 'offline'>('offline');
  const [permissions, setPermissions] = useState<UserPermissions>(DEFAULT_PERMISSIONS);
  const [whoamiContent, setWhoamiContent] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [remindersOpen, setRemindersOpen] = useState(false);
  const [driveOpen, setDriveOpen] = useState(false);
  const [filesOpen, setFilesOpen] = useState(false);
  const [metricsOpen, setMetricsOpen] = useState(false);
  const [serverOpen, setServerOpen] = useState(false);
  const [vpnOpen, setVpnOpen] = useState(false);
  const [ritualsOpen, setRitualsOpen] = useState(false);
  const [tasksOpen, setTasksOpen] = useState(false);
  const [backupsOpen, setBackupsOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [profileOnboarding, setProfileOnboarding] = useState(false);
  const onboardCheckedRef = useRef(false);
  const [uploading, setUploading] = useState(false);
  const [pendingAttachments, setPendingAttachments] = useState<Array<{ name: string; size: number }>>([]);
  const [formModal, setFormModal] = useState<{ visible: boolean; cmd: string; label: string; placeholder: string }>({
    visible: false, cmd: '', label: '', placeholder: ''
  });
  const flatListRef = useRef<FlatList<ChatMessageItem>>(null);
  const [showScrollDown, setShowScrollDown] = useState(false);

  const handleScroll = useCallback(
    (e: { nativeEvent: { contentOffset: { y: number }; contentSize: { height: number }; layoutMeasurement: { height: number } } }) => {
      const { contentOffset, contentSize, layoutMeasurement } = e.nativeEvent;
      const dist = contentSize.height - contentOffset.y - layoutMeasurement.height;
      setShowScrollDown(dist > 240);
    },
    []
  );

  const scrollToBottom = useCallback(() => {
    flatListRef.current?.scrollToEnd({ animated: true });
    setShowScrollDown(false);
  }, []);
  const unsubscribersRef = useRef<(() => void)[]>([]);
  const pendingWhoamiRef = useRef(false);
  const historyLoadedRef = useRef(false);

  useEffect(() => {
    let mounted = true;

    (async () => {
      const stored = await client.loadSession();
      if (!mounted) return;
      if (stored) {
        setSession(stored);
        // Офлайн-кэш: показываем историю мгновенно, не дожидаясь сети/реконнекта.
        // Сервер потом пришлёт свою историю (в connectClient → 'ready') и заменит.
        const cached = await loadCachedHistory();
        if (mounted && cached.length) {
          setMessages((prev) => (prev.length ? prev : cached));
        }
        connectClient(client);
        try {
          const { registerFcm } = await import('../api/fcm');
          registerFcm(stored).catch(() => {});
        } catch {}
      }
    })();

    return () => {
      mounted = false;
      client.disconnect();
      unsubscribersRef.current.forEach((u) => u());
      unsubscribersRef.current = [];
    };
  }, [client]);

  // Сохраняем историю в кэш при изменениях (последние сообщения, без «думает»).
  useEffect(() => {
    if (messages.length) saveCachedHistory(messages);
  }, [messages]);

  useEffect(() => {
    (async () => {
      try {
        const last = await AsyncStorage.getItem('mira:lastUpdateCheck');
        const now = Date.now();
        if (!last || now - parseInt(last, 10) > 86400000) {
          await checkForUpdate(true);
          await AsyncStorage.setItem('mira:lastUpdateCheck', String(now));
        }
      } catch { /* silent fail */ }
    })();
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

  const handleReact = useCallback((id: string, emoji: string) => {
    client.sendReaction(emoji);
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, reaction: emoji } : m)));
  }, []);

  const handleReconnect = useCallback(() => {
    if (!session) return;
    setConnectionStatus('reconnecting');
    client.reconnect().catch(() => setConnectionStatus('offline'));
  }, [client, session]);

  // Авто-реконнект при возврате приложения на экран: пока оно в фоне, JS-таймеры
  // (пинги) заморожены, и сервер рвёт молчащую WS-линию. Возвращаемся — сразу
  // переподключаемся, чтобы не висеть в «офлайн».
  useEffect(() => {
    const sub = AppState.addEventListener('change', (state) => {
      if (state === 'active' && session && !client.connected) {
        client.reconnect().catch(() => {});
      }
    });
    return () => sub.remove();
  }, [client, session]);

  const connectClient = useCallback((c: MiraClient) => {
    unsubscribersRef.current.forEach((u) => u());
    unsubscribersRef.current = [];
    setConnectionStatus('reconnecting');

    const unsubReady = c.on('ready', (msg) => {
      setConnectionStatus('online');
      setUserName(msg.name);
      if (msg.is_owner !== undefined || msg.is_approved !== undefined || msg.gdrive_authorized !== undefined) {
        setPermissions((prev) => ({
          is_owner: msg.is_owner ?? prev.is_owner,
          is_approved: msg.is_approved ?? prev.is_approved,
          gdrive_authorized: msg.gdrive_authorized ?? prev.gdrive_authorized,
          gdrive_email: msg.gdrive_email ?? prev.gdrive_email,
          permissions: msg.permissions ?? prev.permissions,
        }));
      }
      if (msg.counts) setCounts(msg.counts);
      setMood(msg.mood ?? 'default');
      // Owner: подсчёт непрочитанных в тех-канале для бейджа
      if (msg.is_owner) {
        c.listOwnerInbox(0, true).then((items) => {
          setTechUnread(items.length);
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
        c.fetchHistory(50)
          .then((hist) => {
            historyLoadedRef.current = true; // помечаем загруженным только при успехе
            if (hist.messages.length > 0) {
              const historyMsgs: ChatMessageItem[] = hist.messages.map((m) => ({
                id: generateId(),
                type:
                  m.role === 'user' ? 'user' :
                  m.role === 'system' ? 'system' : 'message',
                content: m.content,
                timestamp: m.ts ? Math.round(m.ts * 1000) : 0,
              }));
              // Серверная история — источник истины: заменяем ею кэш-плейсхолдер
              // (показанный на старте). fetchHistory бежит раз за коннект
              // (historyLoadedRef), живых in-flight сообщений тут ещё нет.
              setMessages(historyMsgs);
            }
          })
          .catch(() => {
            // сбой — НЕ помечаем загруженным, повторим на следующем ready
          });
      }
    });

    const unsubAuthRequired = c.on('auth_required', () => {
      setConnectionStatus('offline');
      historyLoadedRef.current = false;
      c.clearSession().catch(() => {});
      Alert.alert('Сессия истекла', 'Пожалуйста, войди снова');
    });

    const unsubThinking = c.on('thinking', () => {
      addMessage({ id: generateId(), type: 'thinking', timestamp: Date.now() });
    });

    const unsubThought = c.on('thought', (msg) => {
      // Заменяем последний thinking/thought на 💭 с действием.
      setMessages((prev) => {
        const idx = [...prev].reverse().findIndex((m) => m.type === 'thinking' || m.type === 'thought');
        if (idx === -1) {
          return [...prev, { id: generateId(), type: 'thought', content: msg.content, timestamp: Date.now() }];
        }
        const realIdx = prev.length - 1 - idx;
        const next = [...prev];
        next[realIdx] = { ...next[realIdx], type: 'thought', content: msg.content };
        return next;
      });
    });

    const unsubMessage = c.on('message', (msg) => {
      addMessage({
        id: generateId(),
        type: 'message',
        content: msg.content,
        attachments: msg.attachments,
        cards: msg.cards,
        timestamp: Date.now(),
      });
    });

    const unsubSystem = c.on('system', (msg) => {
      // Auto-open Google OAuth URLs
      const oauthMatch = msg.content.match(/https:\/\/accounts\.google\.com\/o\/oauth2\/[^\s]+/);
      if (oauthMatch) {
        Linking.openURL(oauthMatch[0]).catch(() => {});
      }
      if (pendingWhoamiRef.current) {
        setWhoamiContent(msg.content);
        pendingWhoamiRef.current = false;
        return;
      }
      addMessage({ id: generateId(), type: 'system', content: msg.content, timestamp: Date.now() });
    });

    const unsubError = c.on('error', (msg) => {
      addMessage({ id: generateId(), type: 'error', content: msg.content, timestamp: Date.now() });
    });

    const unsubPong = c.on('pong', () => {});

    const unsubReaction = c.on('reaction', (msg) => {
      setMessages((prev) => {
        const idx = prev.map((m) => m.type).lastIndexOf('user');
        if (idx < 0) return prev;
        return prev.map((m, i) => (i === idx ? { ...m, reaction: msg.emoji } : m));
      });
    });

    const unsubFiles = c.on('files', (msg) => {
      addMessage({ id: generateId(), type: 'files', files: msg.files, timestamp: Date.now() });
    });

    const unsubGdrive = c.on('gdrive_auth_url', (msg) => {
      addMessage({ id: generateId(), type: 'gdrive_auth_url', url: msg.url, timestamp: Date.now() });
    });

    const unsubPermissions = c.on('permissions_update', (msg) => {
      setPermissions((prev) => ({
        is_owner: msg.is_owner ?? prev.is_owner,
        is_approved: msg.is_approved ?? prev.is_approved,
        gdrive_authorized: msg.gdrive_authorized ?? prev.gdrive_authorized,
        gdrive_email: msg.gdrive_email ?? prev.gdrive_email,
        permissions: msg.permissions ?? prev.permissions,
      }));
    });

    const unsubApproval = c.on('approval_request', (msg) => {
      addMessage({
        id: generateId(),
        type: 'approval_request',
        content: '',
        timestamp: Date.now(),
        approval: {
          user_id: msg.user_id,
          name: msg.name,
          source: msg.source,
        },
      });
    });

    const unsubLearned = c.on('learned', (msg) => {
      addMessage({
        id: generateId(),
        type: 'learned',
        content: msg.insight,
        insight: msg.insight,
        timestamp: Date.now(),
      });
    });

    // Tech-channel: только для unread-badge (полноценный экран — TechScreen)
    const unsubTech = c.onTech((ev) => {
      if (ev.type === 'inbox_update') return;
      if (ev.type === 'thinking' || ev.type === 'message' || ev.type === 'error') return;
      setTechUnread((n) => n + 1);
    });

    unsubscribersRef.current = [
      unsubReady, unsubAuthRequired, unsubThinking, unsubThought, unsubMessage, unsubReaction,
      unsubSystem, unsubError, unsubPong, unsubFiles, unsubGdrive,
      unsubPermissions, unsubApproval, unsubLearned, unsubTech,
    ];

    c.connect().catch(() => setConnectionStatus('offline'));
  }, [addMessage]);

  const handleSend = useCallback(
    (text: string) => {
      if (!client || !session) return;
      const atts = pendingAttachments;
      const displayText = atts.length
        ? `${text}${text ? '\n\n' : ''}${atts.map((a) => '📎 ' + a.name).join('\n')}`
        : text;
      addMessage({
        id: generateId(),
        type: 'user',
        content: displayText,
        timestamp: Date.now(),
      });
      const names = atts.map((a) => a.name);
      client.sendMessage(text, names.length > 0 ? names : undefined);
      if (atts.length) setPendingAttachments([]);
    },
    [client, session, addMessage, pendingAttachments]
  );

  const handleClear = useCallback(() => {
    if (!client) return;
    Alert.alert(
      'Очистить историю?',
      'Действие необратимо.',
      [
        { text: 'Отмена', style: 'cancel' },
        {
          text: 'Очистить',
          style: 'destructive',
          onPress: () => {
            client.sendCommand('clear');
            setMessages([]);
            clearCachedHistory();
          },
        },
      ]
    );
  }, [client]);

  const handleWhoami = useCallback(() => {
    if (!client) return;
    pendingWhoamiRef.current = true;
    client.sendCommand('whoami');
  }, [client]);

  const handlePaletteRun = useCallback(
    (cmd: string) => {
      if (!client) return;
      if (cmd === 'whoami') pendingWhoamiRef.current = true;
      client.sendCommand(cmd);
    },
    [client]
  );

  // Действие из меню: подтверждение — тостом, лента чата не засоряется.
  // image/gdrive_login дают контент в чат — отправляем как есть.
  const handleDrawerRun = useCallback(
    (cmd: string) => {
      if (!client) return;
      const base = cmd.split(' ')[0];
      if (base === 'files') { setFilesOpen(true); return; }
      if (base === 'stats') { setMetricsOpen(true); return; }
      if (base === 'server_stats') { setServerOpen(true); return; }
      if (base === 'vpn_stats') { setVpnOpen(true); return; }
      if (base === 'rituals') { setRitualsOpen(true); return; }
      if (base === 'tasks') { setTasksOpen(true); return; }
      if (base === 'versions') { setBackupsOpen(true); return; }
      if (base === 'clear') { setMessages([]); clearCachedHistory(); }
      if (base === 'image' || base === 'gdrive_login') {
        client.sendCommand(cmd);
        return;
      }
      client
        .sendCommandAwait(cmd, ['system', 'message'])
        .then((m) => {
          const t = 'content' in m ? m.content : 'Готово';
          if (Platform.OS === 'android') ToastAndroid.show(t.slice(0, 160), ToastAndroid.SHORT);
        })
        .catch(() => {});
    },
    [client]
  );

  const handleDrawerRunWithArgs = useCallback(
    (cmd: string, label: string, placeholder: string) => {
      setFormModal({ visible: true, cmd, label, placeholder });
    },
    []
  );

  const handleFetchUsers = useCallback(() => {
    if (!client) return Promise.resolve([]);
    return client
      .sendCommandAwait('users_data', ['users_list'])
      .then((m) => m.users)
      .catch(() => []);
  }, [client]);

  const handleFetchInfo = useCallback((cmd: string): Promise<string> => {
    if (!client) return Promise.resolve('Нет соединения');
    return client
      .sendCommandAwait(cmd, ['system', 'message'])
      .then((m) => ('content' in m ? m.content : '—'))
      .catch(() => 'Не удалось получить данные');
  }, [client]);

  const handleFormSubmit = useCallback(
    (cmdWithArgs: string) => {
      handleDrawerRun(cmdWithArgs); // те же правила: действие → тост, контент → чат
    },
    [handleDrawerRun]
  );

  const handleFileSelect = useCallback(
    async (files: Array<{ uri: string; name: string; type: string }>) => {
      if (!client) return;
      if (pendingAttachments.length + files.length > 5) {
        Alert.alert('Максимум 5 файлов', 'Выбери меньше файлов за раз');
        return;
      }
      setUploading(true);
      const uploaded: Array<{ name: string; size: number }> = [];
      for (const file of files) {
        try {
          const result = await client.uploadFile(file);
          uploaded.push({ name: result.filename, size: result.size });
        } catch (e: unknown) {
          const msg = e instanceof Error ? e.message : 'Ошибка загрузки';
          Alert.alert('Ошибка', `${file.name}: ${msg}`);
        }
      }
      setUploading(false);
      if (uploaded.length > 0) {
        setPendingAttachments((prev) => [...prev, ...uploaded]);
      }
    },
    [client, pendingAttachments]
  );

  const handleClearAttachment = useCallback((index: number) => {
    setPendingAttachments((prev) => prev.filter((_, i) => i !== index));
  }, []);

  const handleFilePress = useCallback(
    (dir: string, name: string) => {
      if (!client) return;
      const url = client.fileUrl(dir as 'inbox' | 'output', name);
      Linking.openURL(url).catch(() => {
        Alert.alert('Ошибка', 'Не удалось открыть файл');
      });
    },
    [client]
  );

  const handleFileLink = useCallback(
    async (url: string) => {
      if (!client) return;
      const base = BASE_URL.replace(/\/$/, '');
      let normalized: string;
      if (url.startsWith('/files/')) {
        normalized = base + url;
      } else if (url.startsWith(`${base}/files/`)) {
        normalized = url;
      } else {
        Linking.openURL(url).catch(() => {});
        return;
      }
      const stored = await client.loadSession();
      if (!stored) {
        Alert.alert('Ошибка', 'Нет активной сессии — войди заново');
        return;
      }
      const sep = normalized.includes('?') ? '&' : '?';
      const urlWithSession = normalized + sep + 'session=' + encodeURIComponent(stored);
      Linking.openURL(urlWithSession).catch(() => {
        Alert.alert('Ошибка', 'Не удалось открыть ссылку');
      });
    },
    [client]
  );

  const handleApprove = useCallback(
    (userId: string) => {
      if (!client) return;
      client.sendCommand(`approve ${userId}`);
      setMessages((prev) =>
        prev.map((m) =>
          m.type === 'approval_request' && m.approval?.user_id === userId
            ? { ...m, approval: { ...m.approval, resolved: 'approve' as const } }
            : m
        )
      );
    },
    [client]
  );

  const handleBlock = useCallback(
    (userId: string) => {
      if (!client) return;
      client.sendCommand(`block ${userId}`);
      setMessages((prev) =>
        prev.map((m) =>
          m.type === 'approval_request' && m.approval?.user_id === userId
            ? { ...m, approval: { ...m.approval, resolved: 'block' as const } }
            : m
        )
      );
    },
    [client]
  );

  const handleOnboarding = useCallback(
    (chip: typeof ONBOARDING_CHIPS[0]) => {
      if (!client) return;
      if (chip.action === 'send') {
        addMessage({ id: generateId(), type: 'user', content: chip.text, timestamp: Date.now() });
        client.sendMessage(chip.text);
      } else {
        client.sendCommand(chip.cmd);
      }
    },
    [client, addMessage]
  );

  const renderMessage = useCallback(
    ({ item, index }: { item: ChatMessageItem; index: number }) => {
      if (item.type === 'approval_request' && item.approval) {
        return (
          <ApprovalCard
            name={item.approval.name}
            userId={item.approval.user_id}
            source={item.approval.source}
            resolved={item.approval.resolved}
            onApprove={() => handleApprove(item.approval!.user_id)}
            onBlock={() => handleBlock(item.approval!.user_id)}
          />
        );
      }
      return (
        <AuroraMessage
          message={item}
          isLast={index === messages.length - 1}
          onFilePress={handleFilePress}
          onFileLink={handleFileLink}
          onReact={item.type === 'message' ? handleReact : undefined}
        />
      );
    },
    [handleApprove, handleBlock, handleFilePress, handleFileLink, handleReact, messages.length]
  );

  return (
    <View style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor={colors.bg.page} />
      <View style={[styles.headerWrap, { paddingTop: insets.top }]}>
        <AuroraTopbar
          connectionStatus={connectionStatus}
          mood={mood}
          onClear={handleClear}
          onCheckUpdate={() => checkForUpdate(false)}
          onWhoami={handleWhoami}
          onOpenDrawer={() => setDrawerOpen(true)}
          onOpenReminders={() => setRemindersOpen(true)}
          onOpenDrive={() => setDriveOpen(true)}
          onReconnect={handleReconnect}
          isOwner={permissions.is_owner}
          onOpenTech={() => { setTechUnread(0); navigation.navigate('Tech'); }}
          techUnread={techUnread}
        />
      </View>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={styles.flex}
        keyboardVerticalOffset={0}
      >
        <FlatList
          ref={flatListRef}
          data={messages}
          extraData={messages.length}
          keyExtractor={(item) => item.id}
          renderItem={renderMessage}
          removeClippedSubviews={true}
          maxToRenderPerBatch={10}
          windowSize={5}
          contentContainerStyle={[
            styles.messagesContainer,
            messages.length === 0 && styles.emptyContainer,
          ]}
          onContentSizeChange={() => flatListRef.current?.scrollToEnd({ animated: true })}
          onLayout={() => flatListRef.current?.scrollToEnd({ animated: false })}
          onScroll={handleScroll}
          scrollEventThrottle={100}
          ListEmptyComponent={
            <AuroraWelcome
              userName={userName}
              chips={ONBOARDING_CHIPS.map((c) => c.label)}
              onChipPress={(text) => {
                const chip = ONBOARDING_CHIPS.find((c) => c.label === text);
                if (chip) handleOnboarding(chip);
              }}
            />
          }
        />
        {showScrollDown && (
          <TouchableOpacity
            style={[styles.scrollDownBtn, { bottom: insets.bottom + 96 }]}
            activeOpacity={0.85}
            onPress={scrollToBottom}
          >
            <Svg width={20} height={20} viewBox="0 0 24 24" fill="none">
              <Path d="M6 9l6 6 6-6" stroke={colors.gold.DEFAULT} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
            </Svg>
          </TouchableOpacity>
        )}
        <AuroraComposer
          onSend={handleSend}
          onSendCommand={handlePaletteRun}
          onFileSelect={handleFileSelect}
          disabled={!session || connectionStatus === 'offline'}
          uploading={uploading}
          pendingAttachments={pendingAttachments}
          onClearAttachment={handleClearAttachment}
        />
      </KeyboardAvoidingView>

      <AuroraSidebar
        visible={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        onRun={handleDrawerRun}
        onRunWithArgs={handleDrawerRunWithArgs}
        permissions={permissions}
        userName={userName}
        connectionStatus={connectionStatus}
        onFetchUsers={handleFetchUsers}
        onFetchInfo={handleFetchInfo}
        onCheckUpdate={() => checkForUpdate(false)}
        onOpenProfile={() => { setDrawerOpen(false); setProfileOnboarding(false); setProfileOpen(true); }}
        counts={counts}
      />
      <CommandFormModal
        visible={formModal.visible}
        cmd={formModal.cmd}
        label={formModal.label}
        placeholder={formModal.placeholder}
        onSubmit={handleFormSubmit}
        onClose={() => setFormModal((p) => ({ ...p, visible: false }))}
      />
      <WhoamiModal visible={!!whoamiContent} content={whoamiContent || ''} onClose={() => setWhoamiContent(null)} />
      <RemindersModal visible={remindersOpen} onClose={() => setRemindersOpen(false)} client={client} />
      <DriveModal visible={driveOpen} onClose={() => setDriveOpen(false)} client={client} />
      <FilesModal visible={filesOpen} onClose={() => setFilesOpen(false)} client={client} session={session} />
      <MetricsModal visible={metricsOpen} onClose={() => setMetricsOpen(false)} client={client} />
      <ServerModal visible={serverOpen} onClose={() => setServerOpen(false)} client={client} />
      <VpnModal visible={vpnOpen} onClose={() => setVpnOpen(false)} client={client} />
      <RitualsModal visible={ritualsOpen} onClose={() => setRitualsOpen(false)} client={client} />
      <TasksModal visible={tasksOpen} onClose={() => setTasksOpen(false)} client={client} />
      <BackupsModal visible={backupsOpen} onClose={() => setBackupsOpen(false)} client={client} />
      <ProfileModal visible={profileOpen} onClose={() => setProfileOpen(false)} client={client} onboarding={profileOnboarding} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg.page },
  headerWrap: { backgroundColor: colors.bg.surface },
  flex: { flex: 1 },
  scrollDownBtn: {
    position: 'absolute',
    right: 16,
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: colors.bg.surface,
    borderWidth: 1,
    borderColor: colors.border.strong,
    alignItems: 'center',
    justifyContent: 'center',
  },
  messagesContainer: { padding: spacing.md, paddingBottom: spacing.xl },
  emptyContainer: { flex: 1, justifyContent: 'center', alignItems: 'center' },
});
