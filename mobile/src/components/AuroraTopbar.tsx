import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { AuroraAvatar } from './ui/AuroraAvatar';
import { AuroraStatusDot } from './ui/AuroraStatusDot';
import { colors, typography, fonts, spacing, radii } from '../theme';

interface Props {
  connectionStatus: 'online' | 'reconnecting' | 'offline';
  onOpenDrawer: () => void;
  onClear: () => void;
  onWhoami: () => void;
  onCheckUpdate: () => void;
  onOpenReminders: () => void;
  onOpenDrive: () => void;
  onReconnect: () => void;
  isOwner?: boolean;
  onOpenTech?: () => void;
  techUnread?: number;
}

export function AuroraTopbar({
  connectionStatus,
  onOpenDrawer,
  onReconnect,
  isOwner,
  onOpenTech,
  techUnread,
}: Props) {
  const statusText = connectionStatus === 'online'
    ? 'на связи · слушает'
    : connectionStatus === 'reconnecting'
    ? 'переподключается...'
    : 'офлайн · нажми ↻';
  const statusColor = connectionStatus === 'online'
    ? colors.gold.DEFAULT
    : connectionStatus === 'reconnecting'
    ? colors.gold.DEFAULT
    : colors.rose;

  return (
    <View style={styles.container}>
      <TouchableOpacity onPress={onOpenDrawer} style={styles.iconBtn} activeOpacity={0.8}>
        <Text style={styles.menuIcon}>☰</Text>
      </TouchableOpacity>

      <AuroraAvatar size={34} glowColor={colors.gold.glow} borderColor={colors.border.strong} />

      <View style={styles.nameBlock}>
        <Text style={styles.name} numberOfLines={1}>Мира</Text>
        {connectionStatus === 'online' ? (
          <View style={styles.statusRow}>
            <AuroraStatusDot color={statusColor} size={5} />
            <Text style={[styles.statusText, { color: statusColor }]} numberOfLines={1}>{statusText}</Text>
          </View>
        ) : (
          <TouchableOpacity
            style={styles.statusRow}
            onPress={onReconnect}
            disabled={connectionStatus === 'reconnecting'}
            activeOpacity={0.7}
          >
            <AuroraStatusDot color={statusColor} size={5} />
            <Text style={[styles.statusText, { color: statusColor }]} numberOfLines={1}>{statusText}</Text>
          </TouchableOpacity>
        )}
      </View>
      {isOwner && onOpenTech && (
        <TouchableOpacity onPress={onOpenTech} style={styles.techBtn} activeOpacity={0.8}>
          <Text style={styles.techIcon}>⚙</Text>
          {techUnread != null && techUnread > 0 && (
            <View style={styles.techBadge}>
              <Text style={styles.techBadgeText}>{techUnread > 99 ? '99+' : techUnread}</Text>
            </View>
          )}
        </TouchableOpacity>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border.divider,
    backgroundColor: colors.bg.page,
  },
  iconBtn: {
    width: 32,
    height: 32,
    borderRadius: radii.pill,
    borderWidth: 1,
    borderColor: colors.border.subtle,
    backgroundColor: 'rgba(255,255,255,0.02)',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: spacing.sm,
  },
  menuIcon: {
    fontSize: 14,
    color: colors.text.dim,
  },
  nameBlock: {
    marginLeft: spacing.sm,
    flex: 1,
  },
  name: {
    ...typography.topbarName,
    color: colors.text.primary,
    fontFamily: fonts.serif,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 2,
  },
  statusText: {
    ...typography.status,
    color: colors.gold.DEFAULT,
    flexShrink: 1,
  },
  actions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  actionIcon: {
    fontSize: 14,
    color: colors.text.dim,
  },
  techBtn: {
    width: 32, height: 32, borderRadius: radii.pill,
    borderWidth: 1, borderColor: colors.border.subtle,
    backgroundColor: 'rgba(255,255,255,0.02)',
    justifyContent: 'center', alignItems: 'center',
    marginLeft: spacing.sm, position: 'relative',
  },
  techIcon: { fontSize: 16, color: colors.gold.DEFAULT },
  techBadge: {
    position: 'absolute', top: -4, right: -4,
    minWidth: 16, height: 16, borderRadius: 8,
    backgroundColor: colors.rose, justifyContent: 'center', alignItems: 'center',
    paddingHorizontal: 4,
  },
  techBadgeText: { color: '#0b1226', fontSize: 9, fontWeight: '700' },
});
