import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { colors, spacing, radii, typography } from '../theme';

interface Props {
  name: string;
  userId: string;
  source: string;
  resolved?: 'approve' | 'block';
  onApprove: () => void;
  onBlock: () => void;
}

export function ApprovalCard({ name, userId, source, resolved, onApprove, onBlock }: Props) {
  if (resolved) {
    return (
      <View style={[styles.card, styles.cardResolved]}>
        <Text style={styles.resolvedText}>
          {resolved === 'approve' ? '✅ Одобрен' : '❌ Заблокирован'}
        </Text>
        <Text style={styles.resolvedSub}>{name} ({userId})</Text>
      </View>
    );
  }

  return (
    <View style={styles.card}>
      <Text style={styles.title}>🔔 Новый пользователь хочет общаться</Text>
      <View style={styles.infoRow}>
        <Text style={styles.infoLabel}>Имя:</Text>
        <Text style={styles.infoValue}>{name}</Text>
      </View>
      <View style={styles.infoRow}>
        <Text style={styles.infoLabel}>ID:</Text>
        <Text style={styles.infoValue}>{userId}</Text>
      </View>
      <View style={styles.infoRow}>
        <Text style={styles.infoLabel}>Откуда:</Text>
        <Text style={styles.infoValue}>{source}</Text>
      </View>
      <View style={styles.actions}>
        <TouchableOpacity style={[styles.btn, styles.approveBtn]} onPress={onApprove}>
          <Text style={styles.approveText}>Одобрить ✅</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[styles.btn, styles.blockBtn]} onPress={onBlock}>
          <Text style={styles.blockText}>Заблокировать ❌</Text>
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.bg.surface,
    borderRadius: radii.card,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border.subtle,
    marginVertical: spacing.sm,
  },
  cardResolved: {
    borderColor: colors.border.subtle,
    opacity: 0.7,
  },
  title: {
    color: colors.gold.DEFAULT,
    fontSize: typography.eventTitle.fontSize,
    fontWeight: typography.eventTitle.fontWeight,
    marginBottom: spacing.md,
  },
  infoRow: {
    flexDirection: 'row',
    marginBottom: spacing.xs,
  },
  infoLabel: {
    color: colors.text.muted,
    fontSize: typography.body.fontSize,
    width: 50,
  },
  infoValue: {
    color: colors.text.primary,
    fontSize: typography.body.fontSize,
    flex: 1,
  },
  actions: {
    flexDirection: 'row',
    gap: spacing.md,
    marginTop: spacing.md,
  },
  btn: {
    flex: 1,
    paddingVertical: spacing.md,
    borderRadius: radii.button,
    alignItems: 'center',
  },
  approveBtn: {
    backgroundColor: colors.sage + '20',
    borderWidth: 1,
    borderColor: colors.sage,
  },
  approveText: {
    color: colors.sage,
    fontWeight: '700',
    fontSize: typography.body.fontSize,
  },
  blockBtn: {
    backgroundColor: colors.rose + '20',
    borderWidth: 1,
    borderColor: colors.rose,
  },
  blockText: {
    color: colors.rose,
    fontWeight: '700',
    fontSize: typography.body.fontSize,
  },
  resolvedText: {
    color: colors.text.primary,
    fontSize: typography.eventTitle.fontSize,
    fontWeight: typography.eventTitle.fontWeight,
    textAlign: 'center',
  },
  resolvedSub: {
    color: colors.text.muted,
    fontSize: typography.body.fontSize,
    textAlign: 'center',
    marginTop: spacing.xs,
  },
});
