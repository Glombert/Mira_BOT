import React, { useCallback, useMemo, useRef, useEffect, useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Animated,
  Dimensions,
  PanResponder,
  ScrollView,
  Linking,
  Image,
  TextInput,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Path, Circle, Rect, G } from 'react-native-svg';
import { colors, spacing, radii, typography, shadow, fonts } from '../theme';
import type { UserPermissions, UserEntry, SidebarCounts } from '../types';
import { APP_VERSION } from '../config';
import { MiraIcon } from './ui/MiraIcon';
import { AuroraAvatar } from './ui/AuroraAvatar';

// Фирменные Aurora-иконки на каждую команду (ключи из дизайн-пакета icons/).
const CMD_ICONS: Record<string, string> = {
  clear: 'clear', whoami: 'profile', tz: 'tz', forget: 'forget', stop: 'stop', help: 'help',
  files: 'myfiles',
  gdrive_login: 'driveLink', gdrive_status: 'driveStatus', gdrive_list: 'driveList',
  gdrive_get: 'driveDown', gdrive_toggle: 'autoup', gdrive_logout: 'driveUnlink',
  gcal: 'cal', gcal_create: 'calNew', gsheet: 'sheetRead', gsheet_create: 'sheetNew',
  remind: 'remNew', reminders: 'remList',
  task: 'taskDefer', tasks: 'taskList',
  image: 'genImg',
  stats: 'metrics', server_stats: 'metrics', vpn_stats: 'metrics', users: 'users', versions: 'backup', evolution_count: 'evolve',
  blacklist: 'blacklist', rituals: 'rituals', reflect: 'review', kidmode: 'child', rename: 'rename',
};
const SECTION_ICONS: Record<string, string> = {
  chat: 'chat', files: 'folder', google: 'cloud', reminders: 'bell',
  tasks: 'task', tools: 'tool', owner: 'lock',
};

const SCREEN_WIDTH = Dimensions.get('window').width;
const DRAWER_WIDTH = Math.min(SCREEN_WIDTH * 0.82, 340);

// ─── Icons (24×24 viewBox) ───────────────────────────────
const IconChat = ({ color = colors.text.primary, size = 18 }: { color?: string; size?: number }) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <Path d="M21 11.5a8.38 8.38 0 01-.9 3.8 8.5 8.5 0 01-7.6 4.7 8.38 8.38 0 01-3.8-.9L3 21l1.9-5.7A8.38 8.38 0 014 11.5a8.5 8.5 0 018.5-8.5 8.38 8.38 0 013.8.9l.9.4" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    <Path d="M22 5l-3 3" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    <Path d="M19 2l3 3" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
  </Svg>
);

const IconFolder = ({ color = colors.text.primary, size = 18 }: { color?: string; size?: number }) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <Path d="M22 19a2 2 0 01-2 2H4a2 2 0 01-2-2V5a2 2 0 012-2h5l2 3h9a2 2 0 012 2z" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
  </Svg>
);

const IconCloud = ({ color = colors.text.primary, size = 18 }: { color?: string; size?: number }) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <Path d="M18 10h-1.26A8 8 0 109 20h9a5 5 0 000-10z" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
  </Svg>
);

const IconBell = ({ color = colors.text.primary, size = 18 }: { color?: string; size?: number }) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <Path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    <Path d="M13.73 21a2 2 0 01-3.46 0" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
  </Svg>
);

const IconClock = ({ color = colors.text.primary, size = 18 }: { color?: string; size?: number }) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <Circle cx="12" cy="12" r="10" stroke={color} strokeWidth={1.5} />
    <Path d="M12 6v6l4 2" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
  </Svg>
);

const IconSparkles = ({ color = colors.text.primary, size = 18 }: { color?: string; size?: number }) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <Path d="M12 3l1.5 4.5L18 9l-4.5 1.5L12 15l-1.5-4.5L6 9l4.5-1.5z" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    <Path d="M5 16l.8 2.3L8 19l-2.3.8L5 22l-.8-2.3L2 19l2.3-.8z" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    <Path d="M19 16l.8 2.3L22 19l-2.3.8L19 22l-.8-2.3L16 19l2.3-.8z" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
  </Svg>
);

const IconShield = ({ color = colors.text.primary, size = 18 }: { color?: string; size?: number }) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <Path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
  </Svg>
);

const IconSearch = ({ color = colors.text.muted, size = 16 }: { color?: string; size?: number }) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <Circle cx="11" cy="11" r="8" stroke={color} strokeWidth={1.5} />
    <Path d="M21 21l-4.35-4.35" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
  </Svg>
);

const IconCommand = ({ color = colors.text.muted, size = 14 }: { color?: string; size?: number }) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <Path d="M4 6h16M4 12h16M4 18h16" stroke={color} strokeWidth={1.5} strokeLinecap="round" />
  </Svg>
);

const IconClose = ({ color = colors.text.muted, size = 16 }: { color?: string; size?: number }) => (
  <Svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <Path d="M18 6L6 18M6 6l12 12" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
  </Svg>
);

const CATEGORY_ICONS: Record<string, React.FC<{ color?: string; size?: number }>> = {
  chat: IconChat,
  files: IconFolder,
  google: IconCloud,
  reminders: IconBell,
  tasks: IconClock,
  tools: IconSparkles,
  owner: IconShield,
};

// ─── Data ────────────────────────────────────────────────
interface SidebarCommand {
  cmd: string;
  label: string;
  category: 'chat' | 'files' | 'google' | 'reminders' | 'tasks' | 'tools' | 'owner';
  requires?: 'gdrive_authorized' | 'owner';
  hasArgs?: boolean;
  argLabel?: string;
  argPlaceholder?: string;
}

const COMMANDS: SidebarCommand[] = [
  // ЧАТ
  { cmd: 'clear', label: 'Очистить историю', category: 'chat' },
  { cmd: 'whoami', label: 'Профиль', category: 'chat' },
  { cmd: 'tz', label: 'Часовой пояс', category: 'chat', hasArgs: true, argLabel: 'Зона (пусто — показать)', argPlaceholder: 'Asia/Khabarovsk или Europe/Moscow' },
  { cmd: 'forget', label: 'Забыть меня', category: 'chat' },
  { cmd: 'stop', label: 'Остановить Конклав', category: 'chat' },
  // ФАЙЛЫ
  { cmd: 'files', label: 'Мои файлы', category: 'files' },
  // GOOGLE
  { cmd: 'gdrive_login', label: 'Привязать Drive', category: 'google' },
  { cmd: 'gdrive_status', label: 'Drive: статус', category: 'google' },
  { cmd: 'gdrive_list', label: 'Файлы на Drive', category: 'google', requires: 'gdrive_authorized' },
  { cmd: 'gdrive_get', label: 'Скачать с Drive', category: 'google', requires: 'gdrive_authorized', hasArgs: true, argLabel: 'ID файла', argPlaceholder: 'вставь ID из Drive' },
  { cmd: 'gdrive_toggle', label: 'Auto-upload', category: 'google', requires: 'gdrive_authorized' },
  { cmd: 'gdrive_logout', label: 'Отвязать Drive', category: 'google', requires: 'gdrive_authorized' },
  { cmd: 'gcal', label: 'Календарь', category: 'google', requires: 'gdrive_authorized' },
  { cmd: 'gcal_create', label: 'Создать событие', category: 'google', requires: 'gdrive_authorized', hasArgs: true, argLabel: 'Событие', argPlaceholder: 'Встреча завтра в 15:00' },
  { cmd: 'gsheet', label: 'Прочитать Таблицу', category: 'google', requires: 'gdrive_authorized', hasArgs: true, argLabel: 'ID таблицы', argPlaceholder: 'вставь ID' },
  { cmd: 'gsheet_create', label: 'Создать Таблицу', category: 'google', requires: 'gdrive_authorized', hasArgs: true, argLabel: 'Название', argPlaceholder: 'Новая таблица' },
  // НАПОМИНАНИЯ
  { cmd: 'remind', label: 'Создать', category: 'reminders', hasArgs: true, argLabel: 'Напоминание', argPlaceholder: '2026-05-25T09:00 Позвонить маме' },
  { cmd: 'reminders', label: 'Список', category: 'reminders' },
  // ЗАДАЧИ
  { cmd: 'task', label: 'Отложить задачу', category: 'tasks', hasArgs: true, argLabel: 'Задача', argPlaceholder: 'завтра 10:00 проверить почту' },
  { cmd: 'tasks', label: 'Список задач', category: 'tasks' },
  // ИНСТРУМЕНТЫ
  { cmd: 'image', label: 'Сгенерировать картинку', category: 'tools', hasArgs: true, argLabel: 'Описание', argPlaceholder: 'кот в космосе, акварель' },
  // ВЛАДЕЛЕЦ
  { cmd: 'stats', label: 'Метрики LLM', category: 'owner', requires: 'owner' },
  { cmd: 'server_stats', label: 'Сервер', category: 'owner', requires: 'owner' },
  { cmd: 'vpn_stats', label: 'VPN', category: 'owner', requires: 'owner' },
  { cmd: 'users', label: 'Пользователи', category: 'owner', requires: 'owner' },
  { cmd: 'versions', label: 'Резервные копии', category: 'owner', requires: 'owner' },
  { cmd: 'evolution_count', label: 'Счётчик /evolve', category: 'owner', requires: 'owner' },
  { cmd: 'blacklist', label: 'Чёрный список', category: 'owner', requires: 'owner' },
  { cmd: 'rituals', label: 'Ритуалы', category: 'owner', requires: 'owner' },
  { cmd: 'reflect', label: 'Само-ревью', category: 'owner', requires: 'owner' },
  { cmd: 'kidmode', label: 'Детский режим', category: 'owner', requires: 'owner', hasArgs: true, argLabel: 'user_id + on/off', argPlaceholder: 'tg_12345 on' },
  { cmd: 'rename', label: 'Переименовать пользователя', category: 'owner', requires: 'owner', hasArgs: true, argLabel: 'user_id + новое имя', argPlaceholder: 'tg_12345 Иван (тестер)' },
  // ПОМОЩЬ
  { cmd: 'help', label: 'Помощь', category: 'chat' },
];

const CATEGORIES: Record<string, { label: string }> = {
  chat: { label: 'ЧАТ' },
  files: { label: 'ФАЙЛЫ' },
  google: { label: 'GOOGLE' },
  reminders: { label: 'НАПОМИНАНИЯ' },
  tasks: { label: 'ЗАДАЧИ' },
  tools: { label: 'ИНСТРУМЕНТЫ' },
  owner: { label: 'ВЛАДЕЛЕЦ' },
};

// ─── Component ───────────────────────────────────────────
interface Props {
  visible: boolean;
  onClose: () => void;
  onRun: (cmd: string) => void;
  onRunWithArgs: (cmd: string, label: string, placeholder: string) => void;
  permissions: UserPermissions;
  userName: string;
  connectionStatus: 'online' | 'reconnecting' | 'offline';
  onFetchUsers?: () => Promise<UserEntry[]>;
  onFetchInfo?: (cmd: string) => Promise<string>;
  onCheckUpdate?: () => void;
  onOpenProfile?: () => void;
  counts?: SidebarCounts;
}

const STATUS_LABEL: Record<string, string> = {
  owner: 'Владелец', regular: 'Одобрен', guest: 'Гость',
  rejected: 'Отклонён', blacklisted: 'Чёрный список', blocked: 'Блок',
};

// Справочные команды: результат показываем панелью прямо в меню (не в чате).
// Это однотекстовые ответы (тип 'system') — sendCommandAwait их перехватывает.
const INFO_CMDS = new Set([
  'whoami', 'help', 'stats', 'versions', 'rituals', 'blacklist',
  'evolution_count', 'gdrive_status', 'gcal', 'reminders', 'tasks',
]);

function CountBadge({ n }: { n: number }) {
  return (
    <View style={styles.countBadge}>
      <Text style={styles.countBadgeText}>{n}</Text>
    </View>
  );
}

export function AuroraSidebar({ visible, onClose, onRun, onRunWithArgs, permissions, userName, connectionStatus, onFetchUsers, onFetchInfo, onCheckUpdate, onOpenProfile, counts = {} }: Props) {
  const countFor = useCallback((cmd: string): number | undefined => {
    const n = ({
      files: counts.files,
      reminders: counts.reminders_today,
      tasks: counts.tasks,
      users: counts.users,
      rituals: counts.rituals,
      evolution_count: counts.evolutions,
    } as Record<string, number | undefined>)[cmd];
    return n && n > 0 ? n : undefined;
  }, [counts]);
  const insets = useSafeAreaInsets();
  const slideAnim = useRef(new Animated.Value(-DRAWER_WIDTH)).current;
  const overlayAnim = useRef(new Animated.Value(0)).current;
  const [searchQuery, setSearchQuery] = useState('');
  const [usersExpanded, setUsersExpanded] = useState(false);
  const [usersList, setUsersList] = useState<UserEntry[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [openUserId, setOpenUserId] = useState<string | null>(null);

  const loadUsers = useCallback(() => {
    if (!onFetchUsers) return;
    setUsersLoading(true);
    onFetchUsers()
      .then((list) => setUsersList(list))
      .catch(() => {})
      .finally(() => setUsersLoading(false));
  }, [onFetchUsers]);

  const toggleUsers = useCallback(() => {
    setUsersExpanded((prev) => {
      const next = !prev;
      if (next && usersList.length === 0) loadUsers();
      return next;
    });
  }, [usersList.length, loadUsers]);

  const userAction = useCallback((cmd: string) => {
    onRun(cmd);
    setOpenUserId(null);
    setTimeout(loadUsers, 600); // обновить список после смены статуса
  }, [onRun, loadUsers]);

  // Справочные команды → результат в раскрывающейся панели (не в чат)
  const [infoOpen, setInfoOpen] = useState<string | null>(null);
  const [infoText, setInfoText] = useState<Record<string, string>>({});
  const [infoLoading, setInfoLoading] = useState<string | null>(null);

  const toggleInfo = useCallback((cmd: string) => {
    setInfoOpen((prev) => {
      if (prev === cmd) return null; // свернуть
      if (onFetchInfo && infoText[cmd] === undefined) {
        setInfoLoading(cmd);
        onFetchInfo(cmd)
          .then((text) => setInfoText((m) => ({ ...m, [cmd]: text })))
          .catch(() => setInfoText((m) => ({ ...m, [cmd]: 'Не удалось получить данные' })))
          .finally(() => setInfoLoading(null));
      }
      return cmd;
    });
  }, [onFetchInfo, infoText]);

  useEffect(() => {
    if (visible) setSearchQuery('');
    Animated.parallel([
      Animated.timing(slideAnim, {
        toValue: visible ? 0 : -DRAWER_WIDTH,
        duration: 280,
        useNativeDriver: true,
      }),
      Animated.timing(overlayAnim, {
        toValue: visible ? 1 : 0,
        duration: 280,
        useNativeDriver: true,
      }),
    ]).start();
  }, [visible, slideAnim, overlayAnim]);

  const panResponder = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_, gestureState) => gestureState.dx > 10,
      onPanResponderMove: (_, gestureState) => {
        if (gestureState.dx < 0) {
          slideAnim.setValue(Math.max(-DRAWER_WIDTH, gestureState.dx));
          overlayAnim.setValue(Math.max(0, 1 + gestureState.dx / DRAWER_WIDTH));
        }
      },
      onPanResponderRelease: (_, gestureState) => {
        if (gestureState.dx < -DRAWER_WIDTH * 0.3) {
          onClose();
        } else {
          Animated.parallel([
            Animated.timing(slideAnim, { toValue: 0, duration: 150, useNativeDriver: true }),
            Animated.timing(overlayAnim, { toValue: 1, duration: 150, useNativeDriver: true }),
          ]).start();
        }
      },
    })
  ).current;

  const isDisabled = useCallback(
    (cmd: SidebarCommand) => {
      if (cmd.requires === 'owner' && !permissions.is_owner) return true;
      if (cmd.requires === 'gdrive_authorized' && !permissions.gdrive_authorized) return true;
      return false;
    },
    [permissions]
  );

  const handlePress = useCallback(
    (cmd: SidebarCommand) => {
      if (isDisabled(cmd)) return;
      if (cmd.hasArgs && cmd.argLabel && cmd.argPlaceholder) {
        onRunWithArgs(cmd.cmd, cmd.argLabel, cmd.argPlaceholder);
      } else {
        onRun(cmd.cmd);
      }
      onClose();
    },
    [isDisabled, onRun, onRunWithArgs, onClose]
  );

  const grouped = useMemo(() => {
    const cats = Object.keys(CATEGORIES);
    return cats.map((cat) => ({
      key: cat,
      ...CATEGORIES[cat],
      commands: COMMANDS.filter((c) => c.category === cat),
    }));
  }, []);

  const filteredGrouped = useMemo(() => {
    if (!searchQuery.trim()) return grouped;
    const q = searchQuery.toLowerCase();
    return grouped
      .map((section) => ({
        ...section,
        commands: section.commands.filter(
          (cmd) =>
            cmd.label.toLowerCase().includes(q) ||
            cmd.cmd.toLowerCase().includes(q)
        ),
      }))
      .filter((section) => section.commands.length > 0);
  }, [grouped, searchQuery]);

  const statusColor =
    connectionStatus === 'online'
      ? colors.sage
      : connectionStatus === 'reconnecting'
      ? colors.gold.DEFAULT
      : colors.rose;

  const statusLabel =
    connectionStatus === 'online'
      ? 'в сети'
      : connectionStatus === 'reconnecting'
      ? 'переподключается...'
      : 'не в сети';

  return (
    <View style={StyleSheet.absoluteFill} pointerEvents={visible ? 'auto' : 'none'}>
      {/* Overlay */}
      <Animated.View
        style={[styles.overlay, { opacity: overlayAnim }]}
        pointerEvents={visible ? 'auto' : 'none'}
      >
        <TouchableOpacity style={StyleSheet.absoluteFill} activeOpacity={1} onPress={onClose} />
      </Animated.View>

      {/* Sidebar panel */}
      <Animated.View
        style={[
          styles.sidebar,
          {
            width: DRAWER_WIDTH,
            paddingTop: insets.top,
            paddingBottom: insets.bottom + spacing.lg,
          },
          { transform: [{ translateX: slideAnim }] },
        ]}
        {...panResponder.panHandlers}
      >
        {/* ── Header: Mira portrait + user ── */}
        <View style={styles.header}>
          <View style={styles.headerAvatarWrap}>
            <AuroraAvatar size={44} glow={false} borderColor={colors.gold.soft} />
            <View style={[styles.statusDot, { backgroundColor: statusColor }]} />
          </View>
          <View style={styles.headerInfo}>
            <Text style={styles.headerName}>{userName || 'Гость'}</Text>
            <Text style={styles.headerStatus}>{statusLabel}</Text>
          </View>
          <TouchableOpacity onPress={onClose} style={styles.closeBtn} activeOpacity={0.7}>
            <IconClose color={colors.text.muted} size={18} />
          </TouchableOpacity>
        </View>

        {/* ── Search ── */}
        <View style={styles.searchWrap}>
          <IconSearch color={colors.text.faint} size={15} />
          <TextInput
            style={styles.searchInput}
            placeholder="Поиск команд..."
            placeholderTextColor={colors.text.faint}
            value={searchQuery}
            onChangeText={setSearchQuery}
            autoCorrect={false}
            autoCapitalize="none"
          />
          {searchQuery.length > 0 && (
            <TouchableOpacity onPress={() => setSearchQuery('')} activeOpacity={0.7}>
              <IconClose color={colors.text.faint} size={14} />
            </TouchableOpacity>
          )}
        </View>

        {/* ── Command sections ── */}
        <ScrollView
          showsVerticalScrollIndicator={false}
          keyboardShouldPersistTaps="handled"
        >
          {filteredGrouped.map((section) => {
            // Hide owner section for non-owners
            if (section.key === 'owner' && !permissions.is_owner) return null;

            // Hide google section if not approved
            if (section.key === 'google' && !permissions.is_approved) {
              return (
                <View key={section.key} style={styles.section}>
                  <View style={styles.sectionHeader}>
                    <MiraIcon name={SECTION_ICONS[section.key] || 'chat'} color={colors.gold.DEFAULT} size={15} />
                    <Text style={styles.sectionTitle}>{section.label}</Text>
                  </View>
                  <Text style={styles.sectionDisabled}>Требуется одобрение</Text>
                </View>
              );
            }

            return (
              <View key={section.key} style={styles.section}>
                <View style={styles.sectionHeader}>
                  <MiraIcon name={SECTION_ICONS[section.key] || 'chat'} color={colors.gold.DEFAULT} size={15} />
                  <Text style={styles.sectionTitle}>{section.label}</Text>
                </View>
                {section.commands.map((cmd) => {
                  const disabled = isDisabled(cmd);

                  // «Пользователи» — раскрывающийся список с подменю действий
                  if (cmd.cmd === 'users' && onFetchUsers && permissions.is_owner && !searchQuery) {
                    return (
                      <View key="users">
                        <TouchableOpacity style={styles.commandRow} onPress={toggleUsers} activeOpacity={0.65}>
                          <MiraIcon name="users" color={colors.text.dim} size={16} />
                          <Text style={styles.commandLabel}>{cmd.label}</Text>
                          {countFor('users') ? <CountBadge n={countFor('users')!} /> : null}
                          <Text style={styles.argsHint}>{usersExpanded ? '▾' : '▸'}</Text>
                        </TouchableOpacity>
                        {usersExpanded && (
                          <View style={styles.userList}>
                            {usersLoading && <Text style={styles.userSub}>Загрузка…</Text>}
                            {!usersLoading && usersList.length === 0 && <Text style={styles.userSub}>Пусто</Text>}
                            {usersList.map((u) => (
                              <View key={u.id}>
                                <TouchableOpacity
                                  style={styles.userRow}
                                  activeOpacity={0.7}
                                  onPress={() => setOpenUserId(openUserId === u.id ? null : u.id)}
                                >
                                  <Text style={styles.userName} numberOfLines={1}>{u.name || u.id}</Text>
                                  <Text style={styles.userStatus}>{STATUS_LABEL[u.status] || u.status}</Text>
                                </TouchableOpacity>
                                {openUserId === u.id && (
                                  <View style={styles.userActions}>
                                    <TouchableOpacity style={styles.userActionBtn} activeOpacity={0.7}
                                      onPress={() => { setOpenUserId(null); onRunWithArgs(`rename ${u.id}`, 'Новое имя', 'Иван'); }}>
                                      <Text style={styles.userActionText}>Переименовать</Text>
                                    </TouchableOpacity>
                                    <TouchableOpacity style={styles.userActionBtn} activeOpacity={0.7}
                                      onPress={() => userAction(`approve ${u.id}`)}>
                                      <Text style={styles.userActionText}>Одобрить</Text>
                                    </TouchableOpacity>
                                    <TouchableOpacity style={styles.userActionBtn} activeOpacity={0.7}
                                      onPress={() => userAction(`reject ${u.id}`)}>
                                      <Text style={styles.userActionText}>Отклонить</Text>
                                    </TouchableOpacity>
                                    <TouchableOpacity style={styles.userActionBtn} activeOpacity={0.7}
                                      onPress={() => userAction(`block ${u.id}`)}>
                                      <Text style={[styles.userActionText, { color: colors.rose }]}>Заблокировать</Text>
                                    </TouchableOpacity>
                                  </View>
                                )}
                              </View>
                            ))}
                          </View>
                        )}
                      </View>
                    );
                  }

                  // «Профиль» — открывает экран профиля, а не info-панель
                  if (cmd.cmd === 'whoami' && onOpenProfile && !searchQuery) {
                    return (
                      <TouchableOpacity key="whoami" style={styles.commandRow} onPress={() => { onClose(); onOpenProfile(); }} activeOpacity={0.65}>
                        <MiraIcon name={CMD_ICONS.whoami || 'chat'} color={colors.text.dim} size={16} />
                        <Text style={styles.commandLabel}>{cmd.label}</Text>
                        <Text style={styles.argsHint}>›</Text>
                      </TouchableOpacity>
                    );
                  }

                  // Справочные команды — раскрываются панелью с результатом, не уходят в чат
                  if (INFO_CMDS.has(cmd.cmd) && onFetchInfo && !disabled && !searchQuery) {
                    const open = infoOpen === cmd.cmd;
                    return (
                      <View key={cmd.cmd}>
                        <TouchableOpacity style={styles.commandRow} onPress={() => toggleInfo(cmd.cmd)} activeOpacity={0.65}>
                          <MiraIcon name={CMD_ICONS[cmd.cmd] || 'chat'} color={colors.text.dim} size={16} />
                          <Text style={styles.commandLabel}>{cmd.label}</Text>
                          {countFor(cmd.cmd) ? <CountBadge n={countFor(cmd.cmd)!} /> : null}
                          <Text style={styles.argsHint}>{open ? '▾' : '▸'}</Text>
                        </TouchableOpacity>
                        {open && (
                          <View style={styles.infoPanel}>
                            {infoLoading === cmd.cmd
                              ? <Text style={styles.userSub}>Загрузка…</Text>
                              : <Text style={styles.infoText} selectable>{infoText[cmd.cmd] || '—'}</Text>}
                          </View>
                        )}
                      </View>
                    );
                  }

                  return (
                    <TouchableOpacity
                      key={cmd.cmd}
                      style={[styles.commandRow, disabled && styles.commandRowDisabled]}
                      onPress={() => handlePress(cmd)}
                      activeOpacity={disabled ? 1 : 0.65}
                    >
                      <MiraIcon
                        name={CMD_ICONS[cmd.cmd] || 'chat'}
                        color={disabled ? colors.text.faint : colors.text.dim}
                        size={16}
                      />
                      <Text style={[styles.commandLabel, disabled && styles.commandLabelDisabled]}>
                        {cmd.label}
                      </Text>
                      {countFor(cmd.cmd) ? <CountBadge n={countFor(cmd.cmd)!} /> : null}
                      {cmd.hasArgs && !disabled && (
                        <Text style={styles.argsHint}>⋯</Text>
                      )}
                    </TouchableOpacity>
                  );
                })}
              </View>
            );
          })}

          {/* ── Footer ── */}
          <View style={styles.footer}>
            <View style={styles.footerDivider} />
            {onCheckUpdate && (
              <TouchableOpacity
                onPress={() => { onCheckUpdate(); onClose(); }}
                activeOpacity={0.7}
                style={styles.footerUpdateBtn}
              >
                <MiraIcon name="autoup" color={colors.gold.DEFAULT} size={15} />
                <Text style={styles.footerUpdate}>Проверить обновление</Text>
              </TouchableOpacity>
            )}
            <TouchableOpacity
              onPress={() => Linking.openURL(`https://github.com/Glombert/Mira_Mobile/releases/tag/v${APP_VERSION}`)}
              activeOpacity={0.7}
            >
              <Text style={styles.footerVersion}>Версия {APP_VERSION}</Text>
            </TouchableOpacity>
            <TouchableOpacity
              onPress={() => Linking.openURL(`https://github.com/Glombert/Mira_Mobile/releases/tag/v${APP_VERSION}`)}
              activeOpacity={0.7}
            >
              <Text style={styles.footerLink}>github.com/Glombert/Mira_Mobile</Text>
            </TouchableOpacity>
          </View>
        </ScrollView>
      </Animated.View>
    </View>
  );
}

// ─── Styles ──────────────────────────────────────────────
const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFill,
    backgroundColor: 'rgba(0, 0, 0, 0.55)',
  },
  sidebar: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    backgroundColor: colors.bg.sidebar,
    borderRightWidth: 1,
    borderRightColor: colors.border.subtle,
    ...shadow.drawer,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.lg,
    borderBottomWidth: 1,
    borderBottomColor: colors.border.divider,
  },
  headerAvatarWrap: {
    position: 'relative',
  },
  headerAvatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    borderWidth: 1.5,
    borderColor: colors.gold.soft,
  },
  statusDot: {
    position: 'absolute',
    bottom: 1,
    right: 1,
    width: 9,
    height: 9,
    borderRadius: 5,
    borderWidth: 2,
    borderColor: colors.bg.sidebar,
  },
  headerInfo: {
    marginLeft: spacing.md,
    flex: 1,
  },
  headerName: {
    ...typography.sidebarName,
    color: colors.text.primary,
  },
  headerStatus: {
    ...typography.status,
    color: colors.text.dim,
    marginTop: 2,
  },
  closeBtn: {
    padding: spacing.sm,
    marginRight: -spacing.sm,
  },
  searchWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    marginHorizontal: spacing.lg,
    marginTop: spacing.lg,
    marginBottom: spacing.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    backgroundColor: colors.bg.surface,
    borderRadius: radii.inputMobile,
    borderWidth: 1,
    borderColor: colors.border.subtle,
  },
  searchInput: {
    flex: 1,
    marginLeft: spacing.sm,
    color: colors.text.primary,
    fontFamily: fonts.sans,
    fontSize: 13,
    lineHeight: 18,
    paddingVertical: 0,
  },
  section: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.lg,
  },
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: spacing.xs,
  },
  sectionTitle: {
    ...typography.sectionLabel,
    color: colors.text.muted,
    marginLeft: spacing.sm,
    textTransform: 'uppercase',
  },
  sectionDisabled: {
    ...typography.sidebarItem,
    color: colors.text.dim,
    paddingVertical: spacing.sm,
    fontStyle: 'italic',
  },
  commandRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 7,
    paddingHorizontal: spacing.sm,
    borderRadius: radii.sidebarItem,
    marginLeft: -spacing.sm,
    marginRight: -spacing.sm,
  },
  commandRowDisabled: {
    opacity: 0.35,
  },
  commandLabel: {
    ...typography.sidebarItem,
    color: colors.text.primary,
    flex: 1,
    marginLeft: spacing.sm,
  },
  commandLabelDisabled: {
    color: colors.text.faint,
  },
  argsHint: {
    color: colors.text.muted,
    fontSize: 14,
    marginLeft: 6,
  },
  countBadge: {
    minWidth: 20,
    height: 18,
    paddingHorizontal: 6,
    borderRadius: 9,
    backgroundColor: 'rgba(245, 188, 122, 0.15)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  countBadgeText: {
    color: colors.gold.DEFAULT,
    fontSize: 11,
    fontWeight: '600',
  },
  userList: {
    marginLeft: spacing.lg,
    marginRight: spacing.sm,
    marginBottom: spacing.xs,
    borderLeftWidth: 1,
    borderLeftColor: colors.border.divider,
    paddingLeft: spacing.sm,
  },
  userSub: {
    color: colors.text.muted,
    fontFamily: fonts.sans,
    fontSize: 12,
    paddingVertical: spacing.xs,
  },
  userRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.xs,
  },
  userName: {
    flex: 1,
    color: colors.text.primary,
    fontFamily: fonts.sans,
    fontSize: 13,
    marginRight: spacing.sm,
  },
  userStatus: {
    color: colors.gold.DEFAULT,
    fontFamily: fonts.mono,
    fontSize: 10,
  },
  userActions: {
    paddingLeft: spacing.sm,
    paddingBottom: spacing.xs,
  },
  userActionBtn: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.sm,
    borderRadius: radii.sidebarItem,
  },
  userActionText: {
    color: colors.text.dim,
    fontFamily: fonts.sans,
    fontSize: 13,
  },
  infoPanel: {
    marginLeft: spacing.lg,
    marginRight: spacing.sm,
    marginBottom: spacing.xs,
    paddingLeft: spacing.sm,
    paddingVertical: spacing.xs,
    borderLeftWidth: 1,
    borderLeftColor: colors.border.divider,
  },
  infoText: {
    color: colors.text.dim,
    fontFamily: fonts.mono,
    fontSize: 12,
    lineHeight: 18,
  },
  footer: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing['3xl'],
    paddingBottom: spacing.lg,
  },
  footerDivider: {
    height: 1,
    backgroundColor: colors.border.divider,
    marginBottom: spacing.md,
  },
  footerUpdateBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.sm,
    marginBottom: spacing.sm,
  },
  footerUpdate: {
    color: colors.gold.DEFAULT,
    fontFamily: fonts.sans,
    fontSize: 13,
    fontWeight: '500',
  },
  footerVersion: {
    ...typography.version,
    color: colors.text.muted,
  },
  footerLink: {
    ...typography.version,
    color: colors.gold.DEFAULT,
    marginTop: spacing.xs,
    textDecorationLine: 'underline',
    textDecorationColor: colors.gold.dim,
  },
});
