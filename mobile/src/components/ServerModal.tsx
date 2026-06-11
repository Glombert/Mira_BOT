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
import type { ServerMessage } from '../types';
import { Sparkline } from './ui/Sparkline';

interface Props {
  visible: boolean;
  onClose: () => void;
  client: MiraClient | null;
}

type ServerStats = Extract<ServerMessage, { type: 'server_stats_data' }>;
type State = 'loading' | 'loaded' | 'error';

function hbText(age: number | null): string {
  if (age === null) return 'нет';
  if (age <= 120) return 'жив';
  return `${Math.round(age / 60)}м назад`;
}

export function ServerModal({ visible, onClose, client }: Props) {
  const insets = useSafeAreaInsets();
  const [data, setData] = useState<ServerStats | null>(null);
  const [state, setState] = useState<State>('loading');
  const [hours, setHours] = useState(24);

  const load = useCallback((h: number) => {
    if (!client) return;
    setState('loading');
    client
      .sendCommandAwait(`server_stats ${h}`, ['server_stats_data', 'system', 'error'], 12000)
      .then((msg: any) => {
        if (msg && msg.type === 'server_stats_data') {
          setData(msg);
          setState('loaded');
        } else {
          setState('error');
        }
      })
      .catch(() => setState('error'));
  }, [client]);

  useEffect(() => {
    if (visible) load(hours);
  }, [visible, hours, load]);

  const pts = data?.points ?? [];
  const periodLabel = hours === 24 ? '24 часа' : '7 дней';

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet">
      <View style={[styles.sheet, { paddingTop: insets.top, paddingBottom: insets.bottom + spacing.lg }]}>
        <View style={styles.header}>
          <TouchableOpacity onPress={onClose} style={styles.closeBtn} activeOpacity={0.7}>
            <Text style={styles.closeBtnText}>✕</Text>
          </TouchableOpacity>
          <Text style={styles.title}>Сервер</Text>
          <View style={styles.toggleWrap}>
            {[24, 168].map((h) => (
              <TouchableOpacity key={h} onPress={() => setHours(h)} activeOpacity={0.7}
                style={[styles.toggle, hours === h && styles.toggleActive]}>
                <Text style={[styles.toggleText, hours === h && styles.toggleTextActive]}>
                  {h === 24 ? '24ч' : '7д'}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        {state === 'loading' && (
          <View style={styles.stateWrap}>
            <ActivityIndicator size="large" color={colors.gold.DEFAULT} />
          </View>
        )}
        {state === 'error' && (
          <View style={styles.stateWrap}>
            <Text style={styles.errorText}>Не удалось получить состояние сервера</Text>
            <TouchableOpacity onPress={() => load(hours)} style={styles.retryBtn} activeOpacity={0.7}>
              <Text style={styles.retryText}>Повторить</Text>
            </TouchableOpacity>
          </View>
        )}

        {state === 'loaded' && data && (
          <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
            <View style={styles.summaryRow}>
              <View style={styles.summaryCard}>
                <Text style={styles.summaryValue}>{data.mem_percent}%</Text>
                <Text style={styles.summaryLabel}>RAM</Text>
              </View>
              <View style={styles.summaryCard}>
                <Text style={styles.summaryValue}>{data.load1.toFixed(2)}</Text>
                <Text style={styles.summaryLabel}>нагрузка</Text>
              </View>
              <View style={styles.summaryCard}>
                <Text style={styles.summaryValue}>{data.disk_free_gb}G</Text>
                <Text style={styles.summaryLabel}>диск своб.</Text>
              </View>
            </View>
            <View style={styles.summaryRow}>
              <View style={styles.summaryCard}>
                <Text style={[styles.summaryValue, { color: data.hb_bot_age !== null && data.hb_bot_age <= 120 ? colors.sage : colors.rose }]}>
                  {hbText(data.hb_bot_age)}
                </Text>
                <Text style={styles.summaryLabel}>бот</Text>
              </View>
              <View style={styles.summaryCard}>
                <Text style={[styles.summaryValue, { color: data.hb_web_age !== null && data.hb_web_age <= 120 ? colors.sage : colors.rose }]}>
                  {hbText(data.hb_web_age)}
                </Text>
                <Text style={styles.summaryLabel}>веб</Text>
              </View>
              <View style={styles.summaryCard}>
                <Text style={styles.summaryValue}>{data.uptime_days}д</Text>
                <Text style={styles.summaryLabel}>аптайм</Text>
              </View>
            </View>

            <Text style={styles.sectionTitle}>RAM · {periodLabel}</Text>
            <View style={styles.chartCard}>
              <Sparkline data={pts.map((p) => p.mem_percent)} color="#f5bc7a" />
            </View>
            <Text style={styles.sectionTitle}>Нагрузка · {periodLabel}</Text>
            <View style={styles.chartCard}>
              <Sparkline data={pts.map((p) => p.load1)} color="#8dd0a7" />
            </View>
            {pts.length < 2 && (
              <Text style={styles.hintText}>Сэмплы копятся раз в 5 минут — графики наполнятся в течение часа.</Text>
            )}
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
  title: { color: colors.text.primary, fontSize: 18, fontWeight: '500', fontFamily: fonts.serif },
  toggleWrap: { flexDirection: 'row', marginLeft: 'auto', gap: spacing.xs },
  toggle: {
    paddingHorizontal: spacing.md, paddingVertical: 6,
    borderRadius: radii.button, borderWidth: 1, borderColor: colors.border.subtle,
  },
  toggleActive: { borderColor: colors.gold.DEFAULT, backgroundColor: 'rgba(245,188,122,0.10)' },
  toggleText: { color: colors.text.muted, fontSize: 12, fontFamily: fonts.mono },
  toggleTextActive: { color: colors.gold.DEFAULT },
  content: { padding: spacing.lg },
  stateWrap: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing['3xl'] },
  errorText: { color: colors.rose, fontSize: 14, textAlign: 'center', marginBottom: spacing.md },
  retryBtn: {
    paddingHorizontal: spacing.xl, paddingVertical: spacing.sm,
    borderRadius: radii.button, borderWidth: 1, borderColor: colors.gold.DEFAULT,
  },
  retryText: { color: colors.gold.DEFAULT, fontSize: 14, fontWeight: '600' },
  summaryRow: { flexDirection: 'row', gap: spacing.md, marginBottom: spacing.md },
  summaryCard: {
    flex: 1, padding: spacing.md, borderRadius: radii.sidebarItem,
    backgroundColor: 'rgba(255,255,255,0.03)', borderWidth: 1, borderColor: colors.border.subtle,
    alignItems: 'center',
  },
  summaryValue: {
    color: colors.gold.DEFAULT, fontSize: 18, fontWeight: '600',
    fontFamily: fonts.mono, marginBottom: 4,
  },
  summaryLabel: {
    color: colors.text.muted, fontSize: 10, fontFamily: fonts.sans,
    textTransform: 'uppercase', letterSpacing: 1,
  },
  sectionTitle: {
    color: colors.text.muted, fontSize: 11, fontFamily: fonts.sans,
    fontWeight: '600', textTransform: 'uppercase', letterSpacing: 1.5,
    marginTop: spacing.lg, marginBottom: spacing.sm,
  },
  chartCard: {
    padding: spacing.md, borderRadius: radii.sidebarItem,
    backgroundColor: 'rgba(255,255,255,0.02)', borderWidth: 1, borderColor: colors.border.divider,
  },
  hintText: {
    color: colors.text.faint, fontSize: 13, marginTop: spacing.md,
    textAlign: 'center', fontFamily: fonts.sans, lineHeight: 20,
  },
});
