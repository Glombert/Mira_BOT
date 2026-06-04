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

interface RitualEntry {
  name: string;
  last_run?: string;
  last_output?: string;
  cadence?: string;
}

interface RitualsData {
  rituals?: RitualEntry[];
}

type State = 'loading' | 'loaded' | 'empty' | 'error';

const IMPORTANCE_COLORS: Record<string, string> = {
  CRITICAL: colors.rose,
  MAJOR: colors.gold.DEFAULT,
  MINOR: colors.sage,
  NONE: colors.text.faint,
};

function extractImportance(output: string): string {
  if (!output) return 'NONE';
  const m = output.match(/IMPORTANCE:\s*(CRITICAL|MAJOR|MINOR|NONE)/i);
  return m ? m[1].toUpperCase() : 'NONE';
}

export function RitualsModal({ visible, onClose, client }: Props) {
  const insets = useSafeAreaInsets();
  const [data, setData] = useState<RitualsData | null>(null);
  const [state, setState] = useState<State>('loading');
  const [errorMsg, setErrorMsg] = useState('');

  const load = useCallback(() => {
    if (!client) return;
    setState('loading');
    client
      .sendCommandAwait('rituals_data', ['rituals_data', 'system', 'error'], 8000)
      .then((msg: any) => {
        if (msg && msg.type === 'rituals_data' && Array.isArray(msg.rituals)) {
          // Мапим структурный контракт в форму этого экрана.
          setData({
            rituals: msg.rituals.map((r: any) => ({
              name: r.name,
              cadence: r.schedule || '',
              last_run: r.last_run || '',
              next_run: r.next_run || '',
              last_output: r.description || '',
            })),
          });
          setState('loaded');
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
          <Text style={styles.title}>Ритуалы</Text>
          <TouchableOpacity onPress={load} style={styles.refreshBtn} activeOpacity={0.7}>
            <Text style={styles.refreshBtnText}>↻</Text>
          </TouchableOpacity>
        </View>

        {state === 'loading' && (
          <View style={styles.stateWrap}>
            <ActivityIndicator size="large" color={colors.gold.DEFAULT} />
            <Text style={styles.stateText}>Загрузка ритуалов...</Text>
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

        {state === 'empty' && (
          <View style={styles.stateWrap}>
            <Text style={styles.emptyIcon}>🔔</Text>
            <Text style={styles.stateText}>Нет ритуалов</Text>
            <Text style={styles.hintText}>Ритуалы настраиваются в конфигах агента</Text>
          </View>
        )}

        {state === 'loaded' && data?.rituals && (
          <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
            {data.rituals.map((r, i) => {
              const imp = extractImportance(r.last_output || '');
              const impColor = IMPORTANCE_COLORS[imp] || colors.text.faint;
              return (
                <View key={i} style={styles.ritualCard}>
                  <View style={styles.ritualHeader}>
                    <Text style={styles.ritualName}>{r.name}</Text>
                    <View style={[styles.impBadge, { backgroundColor: `${impColor}15`, borderColor: `${impColor}40` }]}>
                      <Text style={[styles.impText, { color: impColor }]}>{imp}</Text>
                    </View>
                  </View>
                  {r.cadence ? (
                    <Text style={styles.ritualMeta}>Каденс: {r.cadence}</Text>
                  ) : null}
                  {r.last_run ? (
                    <Text style={styles.ritualMeta}>Запуск: {r.last_run}</Text>
                  ) : null}
                  {r.last_output ? (
                    <Text style={styles.ritualOutput} numberOfLines={4} selectable>
                      {r.last_output.length > 300 ? r.last_output.slice(0, 300) + '…' : r.last_output}
                    </Text>
                  ) : null}
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
  ritualCard: {
    padding: spacing.md, borderRadius: radii.sidebarItem,
    backgroundColor: 'rgba(255,255,255,0.02)', borderWidth: 1,
    borderColor: colors.border.subtle, marginBottom: spacing.md,
  },
  ritualHeader: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    marginBottom: spacing.sm,
  },
  ritualName: {
    color: colors.text.primary, fontSize: 15, fontWeight: '600',
    fontFamily: fonts.sans, flex: 1,
  },
  impBadge: {
    paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999, borderWidth: 1,
  },
  impText: { fontSize: 10, fontWeight: '600', letterSpacing: 0.5 },
  ritualMeta: {
    color: colors.text.muted, fontSize: 11, fontFamily: fonts.mono, marginBottom: 2,
  },
  ritualOutput: {
    color: colors.text.dim, fontSize: 12, fontFamily: fonts.mono,
    lineHeight: 18, marginTop: spacing.sm,
    backgroundColor: 'rgba(0,0,0,0.2)', padding: spacing.sm,
    borderRadius: radii.sidebarItem,
  },
});
