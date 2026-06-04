import React, { useState, useEffect, useCallback } from 'react';
import {
  Modal,
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  StyleSheet,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { colors, spacing, radii, fonts } from '../theme';
import type { MiraClient } from '../api/mira-client';

interface Props {
  visible: boolean;
  onClose: () => void;
  client: MiraClient | null;
}

interface BackupEntry {
  id: string;
  created_at: string;
  size: number;
  type: string;
  fact_count: number;
  note_count: number;
  is_latest: boolean;
}

interface BackupsData {
  schedule: string;
  storage: string;
  backups: BackupEntry[];
}

type State = 'loading' | 'loaded' | 'empty' | 'error';

function fmtSize(bytes: number): string {
  if (!bytes) return '—';
  if (bytes >= 1_073_741_824) return `${(bytes / 1_073_741_824).toFixed(1)} ГБ`;
  if (bytes >= 1_048_576) return `${(bytes / 1_048_576).toFixed(1)} МБ`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} КБ`;
  return `${bytes} Б`;
}

export function BackupsModal({ visible, onClose, client }: Props) {
  const insets = useSafeAreaInsets();
  const [data, setData] = useState<BackupsData | null>(null);
  const [state, setState] = useState<State>('loading');
  const [errorMsg, setErrorMsg] = useState('');

  const load = useCallback(() => {
    if (!client) return;
    setState('loading');
    client
      .sendCommandAwait('backups_data', ['backups_data', 'system', 'error'], 12000)
      .then((msg: any) => {
        if (msg && msg.type === 'backups_data' && Array.isArray(msg.backups)) {
          setData({
            schedule: msg.schedule || '',
            storage: msg.storage || '',
            backups: msg.backups,
          });
          setState(msg.backups.length > 0 ? 'loaded' : 'empty');
        } else {
          setState('empty');
        }
      })
      .catch((e) => {
        setErrorMsg(e?.message || 'Ошибка загрузки');
        setState('error');
      });
  }, [client]);

  useEffect(() => {
    if (visible) load();
  }, [visible, load]);

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet">
      <View style={[styles.sheet, { paddingTop: insets.top, paddingBottom: insets.bottom + spacing.lg }]}>
        <View style={styles.header}>
          <TouchableOpacity onPress={onClose} style={styles.closeBtn} activeOpacity={0.7}>
            <Text style={styles.closeBtnText}>✕</Text>
          </TouchableOpacity>
          <Text style={styles.title}>Резервные копии</Text>
          <TouchableOpacity onPress={load} style={styles.refreshBtn} activeOpacity={0.7}>
            <Text style={styles.refreshBtnText}>↻</Text>
          </TouchableOpacity>
        </View>

        {state === 'loading' && (
          <View style={styles.stateWrap}>
            <ActivityIndicator size="large" color={colors.gold.DEFAULT} />
            <Text style={styles.stateText}>Загрузка копий...</Text>
          </View>
        )}

        {state === 'error' && (
          <View style={styles.stateWrap}>
            <Text style={styles.errorText}>{errorMsg}</Text>
            <TouchableOpacity onPress={load} style={styles.retryBtn} activeOpacity={0.7}>
              <Text style={styles.retryText}>Повторить</Text>
            </TouchableOpacity>
          </View>
        )}

        {(state === 'empty' || state === 'loaded') && (
          <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
            {data && (data.schedule || data.storage) ? (
              <View style={styles.configCard}>
                <Text style={styles.configLabel}>АВТО-КОПИРОВАНИЕ</Text>
                {data.schedule ? (
                  <View style={styles.configRow}>
                    <Text style={styles.configKey}>расписание</Text>
                    <Text style={styles.configVal}>{data.schedule}</Text>
                  </View>
                ) : null}
                {data.storage ? (
                  <View style={styles.configRow}>
                    <Text style={styles.configKey}>хранилище</Text>
                    <Text style={styles.configVal}>{data.storage}</Text>
                  </View>
                ) : null}
              </View>
            ) : null}

            {state === 'empty' && (
              <View style={styles.emptyWrap}>
                <Text style={styles.emptyIcon}>🗄️</Text>
                <Text style={styles.stateText}>Пока нет копий</Text>
                <Text style={styles.hintText}>Снимки памяти создаются по расписанию</Text>
              </View>
            )}

            {data?.backups.map((b, i) => {
              const manual = b.type === 'manual' || b.type === 'вручную';
              const badgeColor = manual ? colors.mystic.DEFAULT : colors.sage;
              return (
                <View key={b.id || i} style={styles.backupCard}>
                  <View style={styles.backupHeader}>
                    <Text style={styles.backupWhen} numberOfLines={1}>{b.created_at || '—'}</Text>
                    {b.is_latest ? (
                      <View style={styles.latestBadge}>
                        <Text style={styles.latestText}>последняя</Text>
                      </View>
                    ) : null}
                    <View style={[styles.typeBadge, { backgroundColor: `${badgeColor}15`, borderColor: `${badgeColor}40` }]}>
                      <Text style={[styles.typeText, { color: badgeColor }]}>{manual ? 'вручную' : 'авто'}</Text>
                    </View>
                  </View>
                  <Text style={styles.backupMeta}>
                    {fmtSize(b.size)} · {b.fact_count} фактов · {b.note_count} заметок
                  </Text>
                </View>
              );
            })}
          </ScrollView>
        )}
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  sheet: { flex: 1, backgroundColor: colors.bg.page },
  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: spacing.lg, paddingVertical: spacing.md,
    borderBottomWidth: 1, borderBottomColor: colors.border.divider,
  },
  closeBtn: { padding: spacing.xs, marginRight: spacing.sm },
  closeBtnText: { color: colors.text.muted, fontSize: 20, fontWeight: '300' },
  refreshBtn: { padding: spacing.xs, marginLeft: 'auto' },
  refreshBtnText: { color: colors.gold.DEFAULT, fontSize: 22 },
  title: {
    color: colors.text.primary, fontSize: 18, fontWeight: '500', fontFamily: fonts.serif,
  },
  content: { padding: spacing.lg },
  stateWrap: {
    flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing['3xl'],
  },
  emptyWrap: {
    alignItems: 'center', justifyContent: 'center', paddingVertical: spacing['3xl'],
  },
  stateText: {
    color: colors.text.dim, fontSize: 15, marginTop: spacing.md, fontFamily: fonts.sans,
  },
  emptyIcon: { fontSize: 48, marginBottom: spacing.md },
  hintText: {
    color: colors.text.faint, fontSize: 13, marginTop: spacing.sm,
    textAlign: 'center', fontFamily: fonts.sans, lineHeight: 20, paddingHorizontal: spacing.xl,
  },
  errorText: {
    color: colors.rose, fontSize: 14, textAlign: 'center', marginBottom: spacing.md,
  },
  retryBtn: {
    paddingHorizontal: spacing.xl, paddingVertical: spacing.sm,
    borderRadius: radii.button, borderWidth: 1, borderColor: colors.gold.DEFAULT,
  },
  retryText: { color: colors.gold.DEFAULT, fontSize: 14, fontWeight: '600' },
  configCard: {
    padding: spacing.md, borderRadius: radii.sidebarItem,
    backgroundColor: 'rgba(255,255,255,0.02)', borderWidth: 1,
    borderColor: colors.border.subtle, marginBottom: spacing.lg,
  },
  configLabel: {
    color: colors.gold.DEFAULT, fontSize: 10, fontWeight: '600',
    letterSpacing: 1.5, marginBottom: spacing.md, fontFamily: fonts.sans,
  },
  configRow: {
    flexDirection: 'row', alignItems: 'center', marginBottom: spacing.xs,
  },
  configKey: { color: colors.text.dim, fontSize: 12, fontFamily: fonts.sans, flex: 1 },
  configVal: { color: colors.text.primary, fontSize: 12, fontFamily: fonts.mono },
  backupCard: {
    padding: spacing.md, borderRadius: radii.sidebarItem,
    backgroundColor: 'rgba(255,255,255,0.02)', borderWidth: 1,
    borderColor: colors.border.subtle, marginBottom: spacing.md,
  },
  backupHeader: {
    flexDirection: 'row', alignItems: 'center', marginBottom: spacing.xs, gap: spacing.sm,
  },
  backupWhen: {
    color: colors.text.primary, fontSize: 14, fontWeight: '500',
    fontFamily: fonts.sans, flex: 1,
  },
  latestBadge: {
    paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999,
    backgroundColor: 'rgba(245,188,122,0.12)', borderWidth: 1, borderColor: 'rgba(245,188,122,0.3)',
  },
  latestText: { color: colors.gold.DEFAULT, fontSize: 10, fontWeight: '600' },
  typeBadge: {
    paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999, borderWidth: 1,
  },
  typeText: { fontSize: 10, fontWeight: '600' },
  backupMeta: {
    color: colors.text.muted, fontSize: 11, fontFamily: fonts.mono,
  },
});
