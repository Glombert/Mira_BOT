import React, { useEffect, useRef, useState, useCallback } from 'react';
import {
  View, Text, StyleSheet, FlatList, TextInput, TouchableOpacity,
  KeyboardAvoidingView, Platform, ActivityIndicator, ToastAndroid,
} from 'react-native';
import Clipboard from '@react-native-clipboard/clipboard';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useNavigation } from '@react-navigation/native';
import Markdown from 'react-native-markdown-display';
import { MiraClient } from '../api/mira-client';
import type { OwnerInboxItem, TechEvent } from '../types';
import { mobileSessionStorage } from '../utils/storage';
import { BASE_URL, IS_MOCK } from '../config';
import { colors, spacing, typography, radii, fonts } from '../theme';

const mdStyles = {
  body: { color: colors.text.primary, fontSize: 14, lineHeight: 20 },
  paragraph: { color: colors.text.primary, fontSize: 14, lineHeight: 20, marginBottom: spacing.sm, marginTop: 0 },
  strong: { color: colors.gold.DEFAULT, fontWeight: '700' as const },
  em: { color: colors.text.primary, fontStyle: 'italic' as const },
  link: { color: colors.gold.DEFAULT, textDecorationLine: 'underline' as const },
  heading1: { color: colors.gold.DEFAULT, fontSize: 18, fontWeight: '700' as const, marginVertical: spacing.sm },
  heading2: { color: colors.gold.DEFAULT, fontSize: 16, fontWeight: '700' as const, marginVertical: spacing.sm },
  heading3: { color: colors.gold.DEFAULT, fontSize: 14, fontWeight: '700' as const, marginVertical: spacing.xs },
  code_inline: {
    backgroundColor: 'rgba(0,0,0,0.4)', color: colors.gold.DEFAULT,
    fontFamily: fonts.mono, fontSize: 13,
    paddingHorizontal: 6, paddingVertical: 1, borderRadius: 4,
  },
  fence: {
    backgroundColor: 'rgba(0,0,0,0.4)', color: colors.text.primary,
    fontFamily: fonts.mono, fontSize: 12, lineHeight: 17,
    padding: spacing.md, borderRadius: radii.sidebarItem,
    marginVertical: spacing.sm,
  },
  blockquote: {
    backgroundColor: 'rgba(0,0,0,0.2)',
    borderLeftWidth: 3, borderLeftColor: colors.gold.DEFAULT,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    marginVertical: spacing.sm,
  },
  bullet_list: { marginLeft: spacing.sm },
  ordered_list: { marginLeft: spacing.sm },
  list_item: { marginBottom: spacing.xs, color: colors.text.primary },
  hr: { backgroundColor: colors.border.subtle, height: 1, marginVertical: spacing.md },
};

// Выделяемый текст в Markdown: long-press → нативные маркеры → «Копировать».
const mdSelectableRules = {
  textgroup: (node: any, children: React.ReactNode, _parent: any, styles: any) => (
    <Text key={node.key} style={styles.textgroup} selectable>
      {children}
    </Text>
  ),
};

type FeedEntry =
  | { kind: 'inbox'; ts: number; item: OwnerInboxItem }
  | { kind: 'msg'; ts: number; role: 'user' | 'assistant'; content: string };

const IMPORTANCE_BORDER: Record<string, string> = {
  CRITICAL: colors.rose,
  MAJOR:    colors.gold.DEFAULT,
  MINOR:    colors.border.strong,
  NONE:     colors.border.subtle,
};

const TYPE_LABEL: Record<string, string> = {
  ritual:           'Ритуал',
  system:           'Система',
  approval_request: 'Заявка',
};

function fmtTime(ts: number | string): string {
  try {
    const d = typeof ts === 'number' ? new Date(ts) : new Date(ts);
    return d.toLocaleString('ru-RU', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' });
  } catch { return String(ts); }
}

export function TechScreen() {
  const insets = useSafeAreaInsets();
  const navigation = useNavigation<any>();
  const [client] = useState(() => new MiraClient({ baseUrl: BASE_URL, mock: IS_MOCK, sessionStorage: mobileSessionStorage }));
  const [inbox, setInbox] = useState<OwnerInboxItem[]>([]);
  const [msgs, setMsgs] = useState<Array<{ role: 'user' | 'assistant'; content: string; ts: number }>>([]);
  const [thinking, setThinking] = useState(false);
  const [thought, setThought] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [busyAction, setBusyAction] = useState<Set<number>>(new Set());
  const listRef = useRef<FlatList<FeedEntry>>(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      await client.loadSession();
      if (!mounted) return;
      // Подтянуть inbox + историю tech
      try {
        const items = await client.listOwnerInbox(0);
        if (mounted) setInbox(items);
        // отметим непрочитанные прочитанными при заходе
        items.filter(it => !it.is_read).forEach(it => {
          client.markInboxRead(it.id).catch(() => {});
        });
      } catch {}
      try {
        const h = await client.fetchHistory(80, 'tech');
        const m = h.messages
          .filter(x => x.role === 'user' || x.role === 'assistant')
          .map(x => ({
            role: x.role as 'user' | 'assistant',
            content: x.content,
            ts: typeof x.ts === 'number' && x.ts > 0 ? Math.round(x.ts * 1000) : Date.now(),
          }));
        if (mounted && m.length) setMsgs(m);
      } catch {}

      const unsubTech = client.onTech((ev: TechEvent) => {
        if (ev.type === 'inbox_update') {
          if (ev.id != null) {
            setInbox(prev => prev.map(it => it.id === ev.id
              ? { ...it, is_read: true, action: ev.action ?? it.action }
              : it));
          }
          return;
        }
        if (ev.type === 'thinking') { setThinking(true); setThought(null); return; }
        if (ev.type === 'thought') { setThinking(true); setThought(ev.content ?? ''); return; }
        if (ev.type === 'message') {
          setThinking(false);
          setThought(null);
          setError(null);
          setMsgs(prev => [...prev, {
            role: 'assistant',
            content: ev.content ?? ev.body ?? '',
            ts: Date.now(),
          }]);
          return;
        }
        if (ev.type === 'error') {
          setThinking(false);
          setThought(null);
          setError(ev.content ?? ev.body ?? 'Ошибка');
          return;
        }
        // ritual / system / approval_request
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
        setInbox(prev => prev.some(p => p.id === item.id && item.id < 1e12) ? prev : [...prev, item]);
      });

      client.connect().catch(() => {});

      return () => unsubTech();
    })();
    return () => { mounted = false; client.disconnect(); };
  }, [client]);

  const feed: FeedEntry[] = [];
  for (const it of inbox) {
    const t = Date.parse(it.ts);
    feed.push({ kind: 'inbox', ts: Number.isFinite(t) ? t : Date.now(), item: it });
  }
  for (const m of msgs) feed.push({ kind: 'msg', ts: m.ts, role: m.role, content: m.content });
  feed.sort((a, b) => a.ts - b.ts);

  const copyAll = useCallback((text: string) => {
    Clipboard.setString(text || '');
    if (Platform.OS === 'android') ToastAndroid.show('Скопировано', ToastAndroid.SHORT);
  }, []);

  const handleSend = useCallback(() => {
    const t = draft.trim();
    if (!t || thinking) return;
    setMsgs(prev => [...prev, { role: 'user', content: t, ts: Date.now() }]);
    setError(null);
    setThought(null);
    setThinking(true);
    client.sendMessage(t, undefined, 'tech');
    setDraft('');
  }, [draft, thinking, client]);

  const applyAction = useCallback(async (id: number, action: 'approve' | 'reject') => {
    if (busyAction.has(id)) return;
    setBusyAction(prev => new Set(prev).add(id));
    try {
      await client.inboxAction(id, action);
      setInbox(prev => prev.map(it => it.id === id ? { ...it, action, is_read: true } : it));
    } finally {
      setBusyAction(prev => { const n = new Set(prev); n.delete(id); return n; });
    }
  }, [client, busyAction]);

  const renderItem = ({ item: entry }: { item: FeedEntry }) => {
    if (entry.kind === 'inbox') {
      const it = entry.item;
      const borderColor = IMPORTANCE_BORDER[it.importance] || colors.border.subtle;
      const label = TYPE_LABEL[it.type] || it.type;
      return (
        <View style={[styles.card, { borderColor }, it.is_read && { opacity: 0.7 }]}>
          <View style={styles.cardHeader}>
            <View style={styles.cardLabelRow}>
              <Text style={styles.cardLabel}>{label}</Text>
              {it.importance && it.importance !== 'NONE' && (
                <Text style={styles.cardImportance}>{it.importance}</Text>
              )}
            </View>
            <View style={styles.cardHeaderRight}>
              <TouchableOpacity onPress={() => copyAll((it.title ? it.title + '\n\n' : '') + it.body)} hitSlop={8}>
                <Text style={styles.copyIcon}>⧉</Text>
              </TouchableOpacity>
              <Text style={styles.cardTs}>{fmtTime(it.ts)}</Text>
            </View>
          </View>
          {!!it.title && <Text style={styles.cardTitle} selectable>{it.title}</Text>}
          <Markdown style={mdStyles} rules={mdSelectableRules}>{it.body}</Markdown>
          {it.type === 'approval_request' && !it.action && (
            <View style={styles.cardActions}>
              <TouchableOpacity
                disabled={busyAction.has(it.id)}
                onPress={() => applyAction(it.id, 'approve')}
                style={[styles.btnPrimary, busyAction.has(it.id) && styles.btnDisabled]}
              >
                <Text style={styles.btnPrimaryText}>Одобрить</Text>
              </TouchableOpacity>
              <TouchableOpacity
                disabled={busyAction.has(it.id)}
                onPress={() => applyAction(it.id, 'reject')}
                style={[styles.btnSecondary, busyAction.has(it.id) && styles.btnDisabled]}
              >
                <Text style={styles.btnSecondaryText}>Отклонить</Text>
              </TouchableOpacity>
            </View>
          )}
          {!!it.action && (
            <Text style={styles.cardActionResult}>
              {it.action === 'approve' ? '✓ одобрено' : it.action === 'reject' ? '✗ отклонено' : `действие: ${it.action}`}
            </Text>
          )}
        </View>
      );
    }
    const mine = entry.role === 'user';
    return (
      <View style={[styles.msgRow, mine ? styles.msgRowRight : styles.msgRowLeft]}>
        <View style={[styles.msgBubble, mine ? styles.msgBubbleMine : styles.msgBubbleHers]}>
          {mine ? (
            <Text style={styles.msgText} selectable>{entry.content}</Text>
          ) : (
            <Markdown style={mdStyles} rules={mdSelectableRules}>{entry.content}</Markdown>
          )}
          <TouchableOpacity onPress={() => copyAll(entry.content)} hitSlop={8} style={styles.copyBtn}>
            <Text style={styles.copyIcon}>⧉ копировать</Text>
          </TouchableOpacity>
        </View>
      </View>
    );
  };

  return (
    <KeyboardAvoidingView
      style={[styles.root, { paddingTop: insets.top }]}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
          <Text style={styles.backIcon}>‹</Text>
        </TouchableOpacity>
        <Text style={styles.title}>Технический канал</Text>
      </View>
      <FlatList
        ref={listRef}
        data={feed}
        keyExtractor={(it, idx) => `${it.kind}-${idx}-${it.ts}`}
        renderItem={renderItem}
        contentContainerStyle={styles.list}
        onContentSizeChange={() => listRef.current?.scrollToEnd({ animated: true })}
        ListEmptyComponent={
          <Text style={styles.emptyHint}>
            Здесь оповещения о ритуалах/сбоях и закрытый разговор с Мирой.
          </Text>
        }
        ListFooterComponent={
          <>
            {thought ? (
              <View style={styles.thinkingRow}>
                <Text style={styles.thinkingText}>💭 {thought}</Text>
              </View>
            ) : thinking ? (
              <View style={styles.thinkingRow}>
                <ActivityIndicator size="small" color={colors.gold.DEFAULT} />
                <Text style={styles.thinkingText}>Мира думает...</Text>
              </View>
            ) : null}
            {!!error && <Text style={styles.errorText}>{error}</Text>}
          </>
        }
      />
      <View style={[styles.inputRow, { paddingBottom: Math.max(insets.bottom, spacing.md) }]}>
        <TextInput
          value={draft}
          onChangeText={setDraft}
          placeholder="Технический вопрос Мире..."
          placeholderTextColor={colors.text.muted}
          editable={!thinking}
          style={styles.input}
          multiline
        />
        <TouchableOpacity
          onPress={handleSend}
          disabled={!draft.trim() || thinking}
          style={[styles.sendBtn, (!draft.trim() || thinking) && styles.btnDisabled]}
        >
          <Text style={styles.sendBtnText}>{thinking ? '...' : 'Отправить'}</Text>
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg.page },
  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    borderBottomWidth: 1, borderBottomColor: colors.border.divider,
  },
  backBtn: { padding: spacing.sm, marginRight: spacing.sm },
  backIcon: { fontSize: 28, color: colors.text.dim, lineHeight: 28 },
  title: { color: colors.text.primary, fontSize: 18, fontFamily: fonts.serif, fontWeight: '500' },
  list: { padding: spacing.md, gap: spacing.sm },
  emptyHint: {
    color: colors.text.muted, textAlign: 'center', marginTop: spacing.xl,
    fontStyle: 'italic', paddingHorizontal: spacing.lg,
  },
  card: {
    borderWidth: 1, borderRadius: radii.card, padding: spacing.md,
    backgroundColor: 'rgba(20, 30, 55, 0.5)', marginBottom: spacing.sm,
  },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.xs },
  cardLabelRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  cardLabel: { color: colors.gold.DEFAULT, fontSize: 11, textTransform: 'uppercase', fontWeight: '700', letterSpacing: 0.8 },
  cardImportance: {
    color: colors.text.primary, fontSize: 10, paddingHorizontal: 6, paddingVertical: 2,
    backgroundColor: 'rgba(245,188,122,0.18)', borderRadius: 4, marginLeft: spacing.xs, fontWeight: '700',
  },
  cardTs: { color: colors.text.dim, fontSize: 11 },
  cardHeaderRight: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  copyIcon: { color: colors.text.muted, fontSize: 12 },
  copyBtn: { alignSelf: 'flex-end', marginTop: spacing.xs },
  cardTitle: { color: colors.gold.DEFAULT, fontSize: 15, fontWeight: '600', marginBottom: spacing.sm },
  cardActions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md },
  cardActionResult: { color: colors.text.muted, fontSize: 11, marginTop: spacing.sm },
  btnPrimary: {
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    backgroundColor: 'rgba(245,188,122,0.2)', borderWidth: 1, borderColor: colors.gold.DEFAULT,
    borderRadius: radii.button,
  },
  btnPrimaryText: { color: colors.gold.DEFAULT, fontSize: 13, fontWeight: '500' },
  btnSecondary: {
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    borderWidth: 1, borderColor: colors.rose, borderRadius: radii.button,
  },
  btnSecondaryText: { color: colors.rose, fontSize: 13, fontWeight: '500' },
  btnDisabled: { opacity: 0.5 },
  msgRow: { marginVertical: spacing.xs },
  msgRowRight: { alignItems: 'flex-end' },
  msgRowLeft: { alignItems: 'flex-start' },
  msgBubble: { maxWidth: '85%', paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radii.card, borderWidth: 1 },
  msgBubbleMine: { backgroundColor: 'rgba(245,188,122,0.1)', borderColor: 'rgba(245,188,122,0.4)' },
  msgBubbleHers: { backgroundColor: 'rgba(255,255,255,0.02)', borderColor: colors.border.subtle },
  msgText: { color: colors.text.primary, fontSize: 14, lineHeight: 20 },
  thinkingRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  thinkingText: { color: colors.text.muted, fontStyle: 'italic', fontSize: 13 },
  errorText: { color: colors.rose, padding: spacing.md, fontSize: 13 },
  inputRow: {
    flexDirection: 'row', alignItems: 'flex-end', gap: spacing.sm,
    padding: spacing.md, borderTopWidth: 1, borderTopColor: colors.border.subtle,
  },
  input: {
    flex: 1, backgroundColor: 'rgba(255,255,255,0.03)', borderWidth: 1, borderColor: colors.border.subtle,
    borderRadius: radii.button, paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    color: colors.text.primary, fontSize: 14, maxHeight: 120,
  },
  sendBtn: {
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    backgroundColor: 'rgba(245,188,122,0.2)', borderWidth: 1, borderColor: colors.gold.DEFAULT,
    borderRadius: radii.button,
  },
  sendBtnText: { color: colors.gold.DEFAULT, fontSize: 13, fontWeight: '500' },
});
