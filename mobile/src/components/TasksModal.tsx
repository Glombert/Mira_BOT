import React, { useState, useEffect, useCallback } from 'react';
import {
  Modal,
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  StyleSheet,
  Alert,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { colors, spacing, radii, typography, fonts } from '../theme';
import type { MiraClient } from '../api/mira-client';

interface Props {
  visible: boolean;
  onClose: () => void;
  client: MiraClient | null;
}

interface TaskEntry {
  id: string;
  message: string;
  trigger_at: string;
  status: string;
}

type State = 'loading' | 'loaded' | 'empty' | 'error';

export function TasksModal({ visible, onClose, client }: Props) {
  const insets = useSafeAreaInsets();
  const [tasks, setTasks] = useState<TaskEntry[]>([]);
  const [state, setState] = useState<State>('loading');
  const [errorMsg, setErrorMsg] = useState('');

  const load = useCallback(() => {
    if (!client) return;
    setState('loading');
    client
      .sendCommandAwait('tasks_data', ['tasks_data', 'system', 'error'], 8000)
      .then((msg: any) => {
        if (msg && msg.type === 'tasks_data' && Array.isArray(msg.tasks)) {
          const parsed: TaskEntry[] = msg.tasks.map((t: any) => ({
            id: String(t.id),
            message: t.message || '',
            trigger_at: t.at || '',
            status: t.status || 'pending',
          }));
          setTasks(parsed);
          setState(parsed.length > 0 ? 'loaded' : 'empty');
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

  const handleCancel = useCallback((taskId: string) => {
    Alert.alert('Отменить задачу?', `ID: ${taskId}`, [
      { text: 'Нет', style: 'cancel' },
      {
        text: 'Отменить',
        style: 'destructive',
        onPress: () => {
          client?.sendCommand(`task_cancel ${taskId}`);
          // Оптимистично убираем
          setTasks((prev) => prev.filter((t) => t.id !== taskId));
          if (tasks.length <= 1) setState('empty');
        },
      },
    ]);
  }, [client, tasks.length]);

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet">
      <View style={[styles.sheet, { paddingTop: insets.top, paddingBottom: insets.bottom + spacing.lg }]}>
        <View style={styles.header}>
          <TouchableOpacity onPress={onClose} style={styles.closeBtn} activeOpacity={0.7}>
            <Text style={styles.closeBtnText}>✕</Text>
          </TouchableOpacity>
          <Text style={styles.title}>Список задач</Text>
          <TouchableOpacity onPress={load} style={styles.refreshBtn} activeOpacity={0.7}>
            <Text style={styles.refreshBtnText}>↻</Text>
          </TouchableOpacity>
        </View>

        {state === 'loading' && (
          <View style={styles.stateWrap}>
            <ActivityIndicator size="large" color={colors.gold.DEFAULT} />
            <Text style={styles.stateText}>Загрузка задач...</Text>
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
            <Text style={styles.emptyIcon}>📋</Text>
            <Text style={styles.stateText}>Нет отложенных задач</Text>
            <Text style={styles.hintText}>
              Создайте задачу: «/task завтра 10:00 проверить почту»
            </Text>
          </View>
        )}

        {state === 'loaded' && (
          <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.content}>
            {tasks.map((t, i) => (
              <View key={t.id || i} style={styles.taskCard}>
                <View style={styles.taskHeader}>
                  <Text style={styles.taskMessage} numberOfLines={3}>{t.message || 'Без названия'}</Text>
                  <TouchableOpacity
                    onPress={() => handleCancel(t.id)}
                    style={styles.cancelBtn}
                    activeOpacity={0.7}
                  >
                    <Text style={styles.cancelBtnText}>✕</Text>
                  </TouchableOpacity>
                </View>
                <View style={styles.taskMeta}>
                  {t.trigger_at ? (
                    <Text style={styles.taskMetaText}>⏰ {t.trigger_at}</Text>
                  ) : null}
                  {t.status ? (
                    <View style={[styles.statusBadge, {
                      backgroundColor: t.status === 'pending' ? 'rgba(141,208,167,0.12)' : 'rgba(255,255,255,0.05)',
                      borderColor: t.status === 'pending' ? 'rgba(141,208,167,0.3)' : colors.border.subtle,
                    }]}>
                      <Text style={[styles.statusText, {
                        color: t.status === 'pending' ? colors.sage : colors.text.muted,
                      }]}>{t.status}</Text>
                    </View>
                  ) : null}
                </View>
              </View>
            ))}
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
  taskCard: {
    padding: spacing.md, borderRadius: radii.sidebarItem,
    backgroundColor: 'rgba(255,255,255,0.02)', borderWidth: 1,
    borderColor: colors.border.subtle, marginBottom: spacing.md,
  },
  taskHeader: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start',
    marginBottom: spacing.sm,
  },
  taskMessage: {
    color: colors.text.primary, fontSize: 14, fontWeight: '500',
    fontFamily: fonts.sans, flex: 1, marginRight: spacing.sm, lineHeight: 20,
  },
  cancelBtn: {
    padding: spacing.xs, borderRadius: radii.sidebarItem,
    backgroundColor: 'rgba(232,138,138,0.08)',
  },
  cancelBtnText: {
    color: colors.rose, fontSize: 12, fontWeight: '600',
  },
  taskMeta: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
  },
  taskMetaText: {
    color: colors.text.muted, fontSize: 11, fontFamily: fonts.mono,
  },
  statusBadge: {
    paddingHorizontal: 8, paddingVertical: 2, borderRadius: 999, borderWidth: 1,
  },
  statusText: { fontSize: 10, fontWeight: '600' },
});
