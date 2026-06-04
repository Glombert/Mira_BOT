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
import { colors, spacing, radii, typography, fonts } from '../theme';
import type { MiraClient } from '../api/mira-client';

interface Props {
  visible: boolean;
  onClose: () => void;
  client: MiraClient | null;
}

interface MetricEntry {
  model: string;
  provider: string;
  calls: number;
  tokens_in: number;
  tokens_out: number;
  cost_est: number;
}

interface MetricsData {
  period?: string;
  models?: MetricEntry[];
  total_calls?: number;
  total_tokens?: number;
  total_cost?: number;
}

type State = 'loading' | 'loaded' | 'empty' | 'error';

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return `${n}`;
}

function formatCost(n: number): string {
  if (n === 0) return '—';
  if (n < 0.01) return '< $0.01';
  return `$${n.toFixed(2)}`;
}

export function MetricsModal({ visible, onClose, client }: Props) {
  const insets = useSafeAreaInsets();
  const [data, setData] = useState<MetricsData | null>(null);
  const [state, setState] = useState<State>('loading');
  const [errorMsg, setErrorMsg] = useState('');

  const load = useCallback(() => {
    if (!client) return;
    setState('loading');
    client
      .sendCommandAwait('metrics_data', ['metrics_data', 'system', 'error'], 8000)
      .then((msg: any) => {
        if (msg && msg.type === 'metrics_data') {
          // Мапим структурный контракт бэкенда в форму этого экрана.
          setData({
            period: `${msg.days ?? 7} дней`,
            total_calls: msg.total_calls ?? 0,
            total_tokens: msg.total_tokens ?? 0,
            total_cost: msg.cost_est ?? 0,
            models: (msg.by_model || []).map((m: any) => ({
              model: m.model,
              provider: '',
              calls: m.calls ?? 0,
              tokens_in: 0,
              tokens_out: m.tokens ?? 0,
              cost_est: m.cost ?? 0,
            })),
          });
          setState('loaded');
        } else if ('content' in msg) {
          setErrorMsg('Нет данных');
          setState('empty');
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
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={onClose} style={styles.closeBtn} activeOpacity={0.7}>
            <Text style={styles.closeBtnText}>✕</Text>
          </TouchableOpacity>
          <Text style={styles.title}>Метрики LLM</Text>
          <TouchableOpacity onPress={load} style={styles.refreshBtn} activeOpacity={0.7}>
            <Text style={styles.refreshBtnText}>↻</Text>
          </TouchableOpacity>
        </View>

        {/* Loading */}
        {state === 'loading' && (
          <View style={styles.stateWrap}>
            <ActivityIndicator size="large" color={colors.gold.DEFAULT} />
            <Text style={styles.stateText}>Загрузка метрик...</Text>
          </View>
        )}

        {/* Error */}
        {state === 'error' && (
          <View style={styles.stateWrap}>
            <Text style={styles.errorText}>{errorMsg}</Text>
            <TouchableOpacity onPress={load} style={styles.retryBtn} activeOpacity={0.7}>
              <Text style={styles.retryText}>Повторить</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Empty */}
        {state === 'empty' && (
          <View style={styles.stateWrap}>
            <Text style={styles.emptyIcon}>📊</Text>
            <Text style={styles.stateText}>Нет данных метрик</Text>
            <Text style={styles.hintText}>Метрики обновляются после LLM-вызовов</Text>
          </View>
        )}

        {/* Loaded */}
        {state === 'loaded' && data && (
          <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
            {/* Totals */}
            {data.total_calls !== undefined && (
              <View style={styles.summaryRow}>
                <View style={styles.summaryCard}>
                  <Text style={styles.summaryValue}>{data.total_calls || 0}</Text>
                  <Text style={styles.summaryLabel}>вызовов</Text>
                </View>
                <View style={styles.summaryCard}>
                  <Text style={styles.summaryValue}>{formatTokens(data.total_tokens || 0)}</Text>
                  <Text style={styles.summaryLabel}>токенов</Text>
                </View>
                <View style={styles.summaryCard}>
                  <Text style={styles.summaryValue}>{formatCost(data.total_cost || 0)}</Text>
                  <Text style={styles.summaryLabel}>затраты</Text>
                </View>
              </View>
            )}

            {/* Model list */}
            {data.models && data.models.length > 0 && (
              <View style={styles.modelsSection}>
                <Text style={styles.sectionTitle}>По моделям</Text>
                {data.models.map((m, i) => (
                  <View key={i} style={styles.modelRow}>
                    <View style={styles.modelMain}>
                      <Text style={styles.modelName} numberOfLines={1}>{m.model}</Text>
                      <Text style={styles.modelProvider}>{m.provider}</Text>
                    </View>
                    <View style={styles.modelStats}>
                      <Text style={styles.modelStat}>{m.calls} вызовов</Text>
                      <Text style={styles.modelStat}>{formatTokens(m.tokens_in + m.tokens_out)} токенов</Text>
                      <Text style={styles.modelCost}>{formatCost(m.cost_est)}</Text>
                    </View>
                  </View>
                ))}
              </View>
            )}

            {/* Plain text fallback */}
            {!data.models && data.period && (
              <Text style={styles.plainText} selectable>{data.period}</Text>
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
  refreshBtn: { padding: spacing.xs, marginLeft: 'auto' },
  refreshBtnText: { color: colors.gold.DEFAULT, fontSize: 22 },
  title: {
    color: colors.text.primary, fontSize: 18, fontWeight: '500', fontFamily: fonts.serif,
  },
  content: { padding: spacing.lg },
  stateWrap: {
    flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing['3xl'],
  },
  stateText: {
    color: colors.text.dim, fontSize: 15, marginTop: spacing.md, fontFamily: fonts.sans,
  },
  emptyIcon: { fontSize: 48, marginBottom: spacing.md },
  hintText: {
    color: colors.text.faint, fontSize: 13, marginTop: spacing.sm,
    textAlign: 'center', fontFamily: fonts.sans, lineHeight: 20,
    paddingHorizontal: spacing.xl,
  },
  errorText: {
    color: colors.rose, fontSize: 14, textAlign: 'center', marginBottom: spacing.md,
  },
  retryBtn: {
    paddingHorizontal: spacing.xl, paddingVertical: spacing.sm,
    borderRadius: radii.button, borderWidth: 1, borderColor: colors.gold.DEFAULT,
  },
  retryText: { color: colors.gold.DEFAULT, fontSize: 14, fontWeight: '600' },
  plainText: {
    color: colors.text.primary, fontSize: 13, fontFamily: fonts.mono, lineHeight: 20,
  },
  summaryRow: {
    flexDirection: 'row', gap: spacing.md, marginBottom: spacing.xl,
  },
  summaryCard: {
    flex: 1, padding: spacing.md, borderRadius: radii.sidebarItem,
    backgroundColor: 'rgba(255,255,255,0.03)', borderWidth: 1, borderColor: colors.border.subtle,
    alignItems: 'center',
  },
  summaryValue: {
    color: colors.gold.DEFAULT, fontSize: 22, fontWeight: '600',
    fontFamily: fonts.mono, marginBottom: 4,
  },
  summaryLabel: {
    color: colors.text.muted, fontSize: 11, fontFamily: fonts.sans,
    textTransform: 'uppercase', letterSpacing: 1,
  },
  modelsSection: { marginTop: spacing.md },
  sectionTitle: {
    color: colors.text.muted, fontSize: 11, fontFamily: fonts.sans,
    fontWeight: '600', textTransform: 'uppercase', letterSpacing: 1.5,
    marginBottom: spacing.md,
  },
  modelRow: {
    paddingVertical: spacing.md, paddingHorizontal: spacing.md,
    borderRadius: radii.sidebarItem,
    backgroundColor: 'rgba(255,255,255,0.02)',
    borderWidth: 1, borderColor: colors.border.divider,
    marginBottom: spacing.xs,
  },
  modelMain: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    marginBottom: spacing.sm,
  },
  modelName: {
    color: colors.text.primary, fontSize: 14, fontWeight: '500', fontFamily: fonts.mono,
    flex: 1, marginRight: spacing.sm,
  },
  modelProvider: {
    color: colors.gold.DEFAULT, fontSize: 11, fontFamily: fonts.sans,
  },
  modelStats: {
    flexDirection: 'row', gap: spacing.lg,
  },
  modelStat: {
    color: colors.text.muted, fontSize: 12, fontFamily: fonts.mono,
  },
  modelCost: {
    color: colors.sage, fontSize: 12, fontFamily: fonts.mono, fontWeight: '500',
  },
});
