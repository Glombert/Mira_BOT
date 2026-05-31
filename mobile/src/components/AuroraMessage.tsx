import React from 'react';
import { View, Text, StyleSheet, Linking, TouchableOpacity } from 'react-native';
import type { ChatMessageItem, MessageCard } from '../types';
import Markdown from 'react-native-markdown-display';
import { TypewriterText } from './ui/TypewriterText';
import { AuroraUserBubble } from './AuroraUserBubble';
import { AuroraMiraBubble } from './AuroraMiraBubble';
import { colors, spacing, radii, typography, fonts } from '../theme';
import { BASE_URL } from '../config';

const _BASE_FILES_PREFIX = `${BASE_URL.replace(/\/$/, '')}/files/`;

function isSameOriginFileLink(url: string): boolean {
  if (url.startsWith('/files/')) return true;
  if (url.startsWith(_BASE_FILES_PREFIX)) return true;
  return false;
}

const _MONTHS = ['янв','фев','мар','апр','мая','июн','июл','авг','сен','окт','ноя','дек'];

function formatTime(ts: number): string {
  if (!ts) return '';
  const d = new Date(ts);
  const now = new Date();
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  if (d.toDateString() === now.toDateString()) return `${hh}:${mm}`;
  const y = new Date(now.getTime() - 86400000);
  if (d.toDateString() === y.toDateString()) return `вчера ${hh}:${mm}`;
  return `${d.getDate()} ${_MONTHS[d.getMonth()]} ${hh}:${mm}`;
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function isFreshMessage(ts: number): boolean {
  return Date.now() - ts < 5000;
}

const mdSelectableRules = {
  textgroup: (node: any, children: React.ReactNode, _parent: any, styles: any) => (
    <Text key={node.key} style={styles.textgroup} selectable>
      {children}
    </Text>
  ),
};

const mdStyles = {
  body: { color: colors.text.primary, fontSize: typography.body.fontSize },
  paragraph: { color: colors.text.primary, fontSize: typography.body.fontSize, marginBottom: spacing.sm },
  link: { color: colors.gold.DEFAULT, textDecorationLine: 'underline' as const },
  strong: { color: colors.text.dim, fontWeight: '700' as const },
  em: { color: colors.text.dim, fontStyle: 'italic' as const },
  code_inline: {
    backgroundColor: colors.bg.surface,
    color: colors.text.dim,
    fontFamily: fonts.mono,
    paddingHorizontal: spacing.xs,
    borderRadius: radii.sidebarItem,
  },
  fence: {
    backgroundColor: colors.bg.surface,
    color: colors.text.dim,
    fontFamily: fonts.mono,
    padding: spacing.md,
    borderRadius: radii.sidebarItem,
    marginVertical: spacing.sm,
  },
  blockquote: {
    backgroundColor: colors.bg.surface,
    borderLeftWidth: 4,
    borderLeftColor: colors.gold.DEFAULT,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    marginVertical: spacing.sm,
  },
  table: {
    borderWidth: 1,
    borderColor: colors.border.subtle,
    marginVertical: spacing.sm,
  },
  thead: { backgroundColor: colors.bg.surface },
  th: {
    color: colors.text.primary,
    backgroundColor: colors.bg.surface,
    padding: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border.subtle,
    fontWeight: '700' as const,
  },
  td: {
    color: colors.text.primary,
    backgroundColor: colors.bg.surface,
    padding: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border.subtle,
  },
  tr: { borderBottomWidth: 1, borderBottomColor: colors.border.subtle },
  hr: {
    backgroundColor: colors.border.subtle,
    height: 1,
    marginVertical: spacing.md,
  },
  heading1: { color: colors.gold.DEFAULT, fontSize: typography.eventTitle.fontSize, fontWeight: '700' as const, marginVertical: spacing.sm },
  heading2: { color: colors.gold.DEFAULT, fontSize: typography.sidebarName.fontSize, fontWeight: '700' as const, marginVertical: spacing.sm },
  heading3: { color: colors.text.dim, fontSize: typography.body.fontSize, fontWeight: '700' as const, marginVertical: spacing.xs },
  bullet_list: { marginLeft: spacing.sm },
  ordered_list: { marginLeft: spacing.sm },
  list_item: { marginBottom: spacing.xs },
};

interface Props {
  message: ChatMessageItem;
  onFilePress?: (dir: string, name: string) => void;
  onFileLink?: (url: string) => void;
  showAvatar?: boolean;
}

const CARD_CONFIG: Record<string, { rgb: string; title: string; icon: string }> = {
  memory: { rgb: '185, 163, 255', title: 'Я заметила', icon: '✨' },
  event: { rgb: '245, 188, 122', title: 'Событие', icon: '🗓' },
  backup: { rgb: '141, 208, 167', title: 'Резервная копия', icon: '🛡' },
};

function MessageCards({ cards }: { cards: MessageCard[] }) {
  return (
    <View style={styles.cardWrap}>
      {cards.map((c, i) => {
        const cfg = CARD_CONFIG[c.kind] || CARD_CONFIG.memory;
        return (
          <View
            key={i}
            style={[styles.card, { backgroundColor: `rgba(${cfg.rgb}, 0.07)`, borderColor: `rgba(${cfg.rgb}, 0.24)` }]}
          >
            <Text style={[styles.cardHeader, { color: `rgb(${cfg.rgb})` }]}>{cfg.icon}  {c.label || cfg.title}</Text>
            {c.fact ? <Text style={styles.cardFact} selectable>{c.fact}</Text> : null}
            {c.list && c.list.length > 0
              ? c.list.map((item, j) => (
                  <Text key={j} style={styles.cardListItem} selectable>·  {item}</Text>
                ))
              : null}
          </View>
        );
      })}
    </View>
  );
}

export function AuroraMessage({ message, onFilePress, onFileLink, showAvatar = true }: Props) {
  const time = message.timestamp ? formatTime(message.timestamp) : undefined;

  if (message.type === 'thinking') {
    return (
      <View style={styles.thinkingBubble}>
        <Text style={styles.thinkingText}>Мира думает</Text>
        <Text style={styles.dots}>...</Text>
      </View>
    );
  }

  if (message.type === 'thought') {
    return (
      <View style={styles.thinkingBubble}>
        <Text style={styles.thinkingText}>💭 {message.content}</Text>
      </View>
    );
  }

  if (message.type === 'user') {
    return (
      <AuroraUserBubble time={time}>
        <Text style={styles.userText} selectable>{message.content}</Text>
      </AuroraUserBubble>
    );
  }

  if (message.type === 'system') {
    return (
      <View style={styles.centerRow}>
        <View style={styles.systemBubble}>
          <Text style={styles.systemText}>{message.content}</Text>
        </View>
      </View>
    );
  }

  if (message.type === 'error') {
    return (
      <View style={styles.centerRow}>
        <View style={styles.errorBubble}>
          <Text style={styles.errorText}>{message.content}</Text>
        </View>
      </View>
    );
  }

  if (message.type === 'files' && message.files) {
    return (
      <View style={styles.centerRow}>
        <View style={styles.systemBubble}>
          <Text style={styles.systemText}>Файлы:</Text>
          {message.files.map((f, i) => (
            <TouchableOpacity key={i} onPress={() => onFilePress?.(f.dir, f.name)}>
              <Text style={styles.fileText}>• {f.name}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </View>
    );
  }

  if (message.type === 'gdrive_auth_url' && message.url) {
    return (
      <View style={styles.centerRow}>
        <View style={styles.systemBubble}>
          <Text style={styles.systemText}>Google Drive авторизация:</Text>
          <Text style={styles.linkText} onPress={() => Linking.openURL(message.url!)}>
            {message.url}
          </Text>
        </View>
      </View>
    );
  }

  // bot message
  const isNew = isFreshMessage(message.timestamp);
  const content = message.content || '';

  return (
    <AuroraMiraBubble time={time} showAvatar={showAvatar}>
      {isNew ? (
        <TypewriterText content={content} isNew={true} />
      ) : (
        <Markdown
          style={mdStyles}
          rules={mdSelectableRules}
          onLinkPress={(url) => {
            if (onFileLink && isSameOriginFileLink(url)) {
              onFileLink(url);
              return true;
            }
            const allowed = ['http:', 'https:', 'miramobile:', 'tg:', 'mailto:', 'file:'];
            try {
              const u = new URL(url);
              if (!allowed.includes(u.protocol)) return true;
            } catch {
              return true;
            }
            Linking.openURL(url);
            return true;
          }}
        >
          {content}
        </Markdown>
      )}
      {message.attachments && message.attachments.length > 0 && (
        <View style={styles.attachmentRow}>
          {message.attachments.map((a, i) => (
            <TouchableOpacity key={i} style={styles.attachmentChip} onPress={() => onFilePress?.(a.dir, a.name)}>
              <Text style={styles.attachmentChipText} numberOfLines={1}>
                📎 {a.name} · {formatBytes(a.size)}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
      )}
      {message.cards && message.cards.length > 0 && <MessageCards cards={message.cards} />}
    </AuroraMiraBubble>
  );
}

const styles = StyleSheet.create({
  userText: { color: colors.text.primary, fontSize: typography.body.fontSize },
  centerRow: { alignSelf: 'center', marginVertical: spacing.sm, maxWidth: '90%' },
  systemBubble: {
    backgroundColor: colors.bg.surface,
    borderRadius: radii.button,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.border.subtle,
    alignItems: 'center',
  },
  systemText: { color: colors.text.muted, fontSize: typography.status.fontSize },
  errorBubble: {
    backgroundColor: '#3a1010',
    borderRadius: radii.button,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: '#5a2020',
  },
  errorText: { color: colors.rose, fontSize: typography.status.fontSize },
  thinkingBubble: {
    flexDirection: 'row',
    alignSelf: 'center',
    alignItems: 'center',
    gap: 6,
    padding: spacing.sm,
  },
  thinkingText: { color: colors.text.muted, fontSize: typography.status.fontSize },
  dots: { color: colors.gold.DEFAULT, fontSize: typography.status.fontSize },
  fileText: { color: colors.text.dim, fontSize: typography.status.fontSize, marginTop: spacing.xs },
  linkText: {
    color: colors.gold.DEFAULT,
    fontSize: typography.status.fontSize,
    textDecorationLine: 'underline',
    marginTop: spacing.xs,
  },
  attachmentRow: { marginTop: spacing.md, gap: spacing.xs },
  attachmentChip: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: colors.bg.page,
    borderRadius: radii.sidebarItem,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border.strong,
  },
  attachmentChipText: { color: colors.text.dim, fontSize: typography.body.fontSize },
  cardWrap: { marginTop: spacing.sm, gap: spacing.xs },
  card: {
    borderRadius: radii.sidebarItem,
    borderWidth: 1,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  cardHeader: {
    fontSize: 12,
    fontWeight: '600',
    marginBottom: 4,
    fontFamily: fonts.sans,
  },
  cardFact: { color: colors.text.primary, fontSize: typography.body.fontSize, lineHeight: 20 },
  cardListItem: { color: colors.text.dim, fontSize: 13, lineHeight: 19, marginTop: 2 },
});
