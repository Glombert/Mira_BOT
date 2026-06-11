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
import { MultiLineChart } from './ui/MultiLineChart';

interface Props {
  visible: boolean;
  onClose: () => void;
  client: MiraClient | null;
}

type VpnStats = Extract<ServerMessage, { type: 'vpn_stats_data' }>;
type State = 'loading' | 'loaded' | 'error';

function fmtMb(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)}G`;
  return `${Math.round(mb)}M`;
}

function fmtMinutes(min: number): string {
  if (min >= 60) return `${Math.floor(min / 60)}ч ${min % 60}м`;
  return `${min}м`;
}

function lastSeen(min: number | null): string {
  if (min == null || Number.isNaN(min)) return 'не подключался';
  if (min < 3) return 'сейчас';
  if (min < 60) return `${min} мин назад`;
  if (min < 1440) return `${Math.round(min / 60)} ч назад`;
  return `${Math.round(min / 1440)} дн назад`;
}

const PEER_COLORS = ['#f5bc7a', '#8dd0a7', '#b9a3ff', '#7aa6f5', '#e88a8a', '#e0c068', '#6fd0c8', '#d98ec4'];

export function VpnModal({ visible, onClose, client }: Props) {
  const insets = useSafeAreaInsets();
  const [data, setData] = useState<VpnStats | null>(null);
  const [state, setState] = useState<State>('loading');
  const [hours, setHours] = useState(24);

  const load = useCallback((h: number) => {
    if (!client) return;
    setState('loading');
    client
      .sendCommandAwait(`vpn_stats ${h}`, ['vpn_stats_data', 'system', 'error'], 15000)
      .then((msg: any) => {
        if (msg && msg.type === 'vpn_stats_data') {
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
  const totalMb = (data?.peers ?? []).reduce((s, p) => s + p.rx_mb + p.tx_mb, 0);
  const periodLabel = hours === 24 ? '24 часа' : '7 дней';

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet">
      <View style={[styles.sheet, { paddingTop: insets.top, paddingBottom: insets.bottom + spacing.lg }]}>
        <View style={styles.header}>
          <TouchableOpacity onPress={onClose} style={styles.closeBtn} activeOpacity={0.7}>
            <Text style={styles.closeBtnText}>✕</Text>
          </TouchableOpacity>
          <Text style={styles.title}>VPN</Text>
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
            <Text style={styles.errorText}>Не удалось получить состояние VPN</Text>
            <TouchableOpacity onPress={() => load(hours)} style={styles.retryBtn} activeOpacity={0.7}>
              <Text style={styles.retryText}>Повторить</Text>
            </TouchableOpacity>
          </View>
        )}

        {state === 'loaded' && data && (
          <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
            <View style={styles.summaryRow}>
              <View style={styles.summaryCard}>
                <Text style={[styles.summaryValue, { color: data.bridge_ok ? colors.sage : colors.rose }]}>
                  {data.bridge_ok ? 'жив' : 'упал'}
                </Text>
                <Text style={styles.summaryLabel}>
                  мост{data.bridge_latency_ms != null ? ` · ${data.bridge_latency_ms}мс` : ''}
                </Text>
              </View>
              <View style={styles.summaryCard}>
                <Text style={[styles.summaryValue, { color: data.wg_up ? colors.sage : colors.rose }]}>
                  {data.wg_up ? 'жив' : 'лежит'}
                </Text>
                <Text style={styles.summaryLabel}>wireguard</Text>
              </View>
              <View style={styles.summaryCard}>
                <Text style={styles.summaryValue}>{data.peers_online}/{data.peers.length}</Text>
                <Text style={styles.summaryLabel}>онлайн</Text>
              </View>
              <View style={styles.summaryCard}>
                <Text style={styles.summaryValue}>{fmtMb(totalMb)}</Text>
                <Text style={styles.summaryLabel}>трафик</Text>
              </View>
            </View>

            <Text style={styles.sectionTitle}>Трафик по устройствам · {periodLabel}</Text>
            <View style={styles.chartCard}>
              <MultiLineChart
                series={data.traffic_series ?? []}
                lines={data.peers.map((p, i) => ({ name: p.name, color: PEER_COLORS[i % PEER_COLORS.length] }))}
              />
              <View style={styles.legend}>
                {data.peers.map((p, i) => (
                  <View key={i} style={styles.legendItem}>
                    <View style={[styles.legendDot, { backgroundColor: PEER_COLORS[i % PEER_COLORS.length] }]} />
                    <Text style={styles.legendText} numberOfLines={1}>{p.name}</Text>
                  </View>
                ))}
              </View>
            </View>
            <Text style={styles.sectionTitle}>Пинг моста · {periodLabel}</Text>
            <View style={styles.chartCard}>
              <Sparkline data={(data.bridge_points ?? []).map((p) => p.latency_ms ?? 0)} color="#7aa6f5" />
            </View>

            <Text style={styles.sectionTitle}>Устройства · {periodLabel}</Text>
            {data.peers.map((p, i) => (
              <View key={i} style={styles.peerRow}>
                <View style={styles.peerMain}>
                  <View style={[styles.colorTag, { backgroundColor: PEER_COLORS[i % PEER_COLORS.length] }]} />
                  <View style={[styles.dot, { backgroundColor: p.online ? colors.sage : colors.border.subtle }]} />
                  <Text style={styles.peerName} numberOfLines={1}>{p.name}</Text>
                  <Text style={styles.peerKind}>{p.kind === 'reality' ? 'Reality' : 'WG'}</Text>
                  <Text style={styles.peerStatus}>{p.online ? 'онлайн' : lastSeen(p.last_seen_min)}</Text>
                </View>
                <View style={styles.peerStats}>
                  <Text style={styles.peerStat}>в сети {fmtMinutes(p.online_minutes)}</Text>
                  <Text style={styles.peerStat}>↓ {fmtMb(p.rx_mb)}</Text>
                  <Text style={styles.peerStat}>↑ {fmtMb(p.tx_mb)}</Text>
                </View>
              </View>
            ))}
            {!data.peers.length && (
              <Text style={styles.hintText}>Пиров пока нет — добавь устройство: scripts/wg_add_peer.sh «имя» на сервере.</Text>
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
  summaryRow: { flexDirection: 'row', gap: spacing.sm, marginBottom: spacing.md },
  summaryCard: {
    flex: 1, padding: spacing.sm, borderRadius: radii.sidebarItem,
    backgroundColor: 'rgba(255,255,255,0.03)', borderWidth: 1, borderColor: colors.border.subtle,
    alignItems: 'center',
  },
  summaryValue: {
    color: colors.gold.DEFAULT, fontSize: 15, fontWeight: '600',
    fontFamily: fonts.mono, marginBottom: 4,
  },
  summaryLabel: {
    color: colors.text.muted, fontSize: 9, fontFamily: fonts.sans,
    textTransform: 'uppercase', letterSpacing: 0.8,
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
  legend: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md, marginTop: spacing.sm },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  legendDot: { width: 9, height: 9, borderRadius: 2 },
  legendText: { color: colors.text.dim, fontSize: 11, fontFamily: fonts.sans },
  peerRow: {
    paddingVertical: spacing.md, paddingHorizontal: spacing.md,
    borderRadius: radii.sidebarItem,
    backgroundColor: 'rgba(255,255,255,0.02)',
    borderWidth: 1, borderColor: colors.border.divider,
    marginBottom: spacing.xs,
  },
  peerMain: { flexDirection: 'row', alignItems: 'center', marginBottom: spacing.sm },
  colorTag: { width: 4, height: 16, borderRadius: 2, marginRight: spacing.sm },
  dot: { width: 8, height: 8, borderRadius: 4, marginRight: spacing.sm },
  peerName: { color: colors.text.primary, fontSize: 14, fontWeight: '500', flex: 1, fontFamily: fonts.sans },
  peerKind: {
    color: colors.text.muted, fontSize: 9, fontFamily: fonts.mono,
    textTransform: 'uppercase', letterSpacing: 0.5,
    backgroundColor: 'rgba(255,255,255,0.05)', paddingHorizontal: 5, paddingVertical: 2,
    borderRadius: 4, marginRight: spacing.sm, overflow: 'hidden',
  },
  peerStatus: { color: colors.text.muted, fontSize: 12, fontFamily: fonts.sans },
  peerStats: { flexDirection: 'row', gap: spacing.lg },
  peerStat: { color: colors.text.muted, fontSize: 12, fontFamily: fonts.mono },
  hintText: {
    color: colors.text.faint, fontSize: 13, marginTop: spacing.md,
    textAlign: 'center', fontFamily: fonts.sans, lineHeight: 20,
  },
});
