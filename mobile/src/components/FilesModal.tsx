import React, { useState, useEffect, useCallback } from 'react';
import {
  Modal,
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  Linking,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import type { MiraClient } from '../api/mira-client';
import type { Attachment } from '../types';
import { colors, spacing, radii, typography, fonts } from '../theme';
import { BASE_URL } from '../config';

const _FILES_PREFIX = `${BASE_URL.replace(/\/$/, '')}/files/`;

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

const FILE_EMOJI: Record<string, string> = {
  pdf: '📄', doc: '📝', docx: '📝', xls: '📊', xlsx: '📊', csv: '📊',
  m4a: '🎙', mp3: '🎵', wav: '🎵', flac: '🎵',
  png: '🖼', jpg: '🖼', jpeg: '🖼', gif: '🖼', svg: '🖼', webp: '🖼',
  zip: '📦', tar: '📦', gz: '📦', rar: '📦',
  txt: '📃', md: '📃', json: '📃', xml: '📃', yaml: '📃',
  py: '🐍', js: '📜', ts: '📜', tsx: '📜',
};

function emoji(name: string) {
  const ext = (name.split('.').pop() || '').toLowerCase();
  return FILE_EMOJI[ext] || '📎';
}

interface Props {
  visible: boolean;
  onClose: () => void;
  client: MiraClient | null;
  session?: string | null;
}

type State = 'loading' | 'loaded' | 'empty' | 'error';

export function FilesModal({ visible, onClose, client, session }: Props) {
  const insets = useSafeAreaInsets();
  const [files, setFiles] = useState<Attachment[]>([]);
  const [state, setState] = useState<State>('loading');
  const [errorMsg, setErrorMsg] = useState('');

  const loadFiles = useCallback(() => {
    if (!client) return;
    setState('loading');
    client
      .sendCommandAwait('files', ['files', 'system', 'error'], 10000)
      .then((msg) => {
        if ('files' in msg && msg.files) {
          const list = msg.files as Attachment[];
          setFiles(list);
          setState(list.length > 0 ? 'loaded' : 'empty');
        } else if ('content' in msg) {
          setErrorMsg(msg.content || 'Не удалось загрузить');
          setState('error');
        } else {
          setState('empty');
        }
      })
      .catch((e) => {
        setErrorMsg(e?.message || 'Ошибка сети');
        setState('error');
      });
  }, [client]);

  useEffect(() => {
    if (visible) loadFiles();
  }, [visible, loadFiles]);

  const handleFilePress = useCallback((dir: string, name: string) => {
    const url = `${_FILES_PREFIX}${dir}/${encodeURIComponent(name)}?session=${session || ''}`;
    Linking.openURL(url).catch(() => {});
  }, [session]);

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="pageSheet">
      <View style={[styles.sheet, { paddingTop: insets.top, paddingBottom: insets.bottom + spacing.lg }]}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity onPress={onClose} style={styles.closeBtn} activeOpacity={0.7}>
            <Text style={styles.closeBtnText}>✕</Text>
          </TouchableOpacity>
          <Text style={styles.title}>Мои файлы</Text>
          <TouchableOpacity onPress={loadFiles} style={styles.refreshBtn} activeOpacity={0.7}>
            <Text style={styles.refreshBtnText}>↻</Text>
          </TouchableOpacity>
        </View>

        {/* Count */}
        {state === 'loaded' && (
          <Text style={styles.count}>{files.length} файлов</Text>
        )}

        {/* State: loading */}
        {state === 'loading' && (
          <View style={styles.stateWrap}>
            <ActivityIndicator size="large" color={colors.gold.DEFAULT} />
            <Text style={styles.stateText}>Загрузка файлов...</Text>
          </View>
        )}

        {/* State: error */}
        {state === 'error' && (
          <View style={styles.stateWrap}>
            <Text style={styles.errorText}>{errorMsg}</Text>
            <TouchableOpacity onPress={loadFiles} style={styles.retryBtn} activeOpacity={0.7}>
              <Text style={styles.retryText}>Повторить</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* State: empty */}
        {state === 'empty' && (
          <View style={styles.stateWrap}>
            <Text style={styles.emptyIcon}>📂</Text>
            <Text style={styles.stateText}>У вас пока нет файлов</Text>
            <Text style={styles.hintText}>
              Попросите Миру создать файл или загрузите его через чат
            </Text>
          </View>
        )}

        {/* State: loaded — file grid */}
        {state === 'loaded' && (
          <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={styles.grid}>
            {files.map((f, i) => (
              <TouchableOpacity
                key={`${f.dir || ''}-${f.name}-${i}`}
                style={styles.card}
                activeOpacity={0.7}
                onPress={() => handleFilePress(f.dir, f.name)}
              >
                <View style={styles.cardTop}>
                  <View style={styles.iconWrap}>
                    <Text style={styles.icon}>{emoji(f.name)}</Text>
                  </View>
                  {f.dir === 'inbox' && (
                    <View style={styles.dirBadge}>
                      <Text style={styles.dirBadgeText}>📥 входящие</Text>
                    </View>
                  )}
                </View>
                <Text style={styles.fileName} numberOfLines={2}>{f.name}</Text>
                <Text style={styles.fileMeta}>
                  {f.size ? formatBytes(f.size) : ''}
                  {f.dir ? ` · ${f.dir === 'output' ? '💾 создано Мирой' : '📥 входящие'}` : ''}
                </Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        )}
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  sheet: {
    flex: 1,
    backgroundColor: colors.bg.page,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
    borderBottomColor: colors.border.divider,
  },
  closeBtn: { padding: spacing.xs, marginRight: spacing.sm },
  closeBtnText: { color: colors.text.muted, fontSize: 20, fontWeight: '300' },
  refreshBtn: { padding: spacing.xs, marginLeft: 'auto' },
  refreshBtnText: { color: colors.gold.DEFAULT, fontSize: 22 },
  title: {
    color: colors.text.primary,
    fontSize: 18,
    fontWeight: '500',
    fontFamily: fonts.serif,
  },
  count: {
    color: colors.text.muted,
    fontSize: 13,
    fontFamily: fonts.mono,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.xs,
  },
  stateWrap: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing['3xl'],
  },
  stateText: {
    color: colors.text.dim,
    fontSize: 15,
    marginTop: spacing.md,
    fontFamily: fonts.sans,
  },
  emptyIcon: {
    fontSize: 48,
    marginBottom: spacing.md,
  },
  hintText: {
    color: colors.text.faint,
    fontSize: 13,
    marginTop: spacing.sm,
    textAlign: 'center',
    fontFamily: fonts.sans,
    lineHeight: 20,
    paddingHorizontal: spacing.xl,
  },
  errorText: {
    color: colors.rose,
    fontSize: 14,
    textAlign: 'center',
    marginBottom: spacing.md,
  },
  retryBtn: {
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm,
    borderRadius: radii.button,
    borderWidth: 1,
    borderColor: colors.gold.DEFAULT,
  },
  retryText: {
    color: colors.gold.DEFAULT,
    fontSize: 14,
    fontWeight: '600',
  },
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    padding: spacing.md,
    gap: spacing.md,
  },
  card: {
    width: '47%',
    padding: spacing.md,
    borderRadius: radii.sidebarItem,
    backgroundColor: 'rgba(255,255,255,0.02)',
    borderWidth: 1,
    borderColor: colors.border.subtle,
  },
  cardTop: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  iconWrap: {
    width: 32,
    height: 32,
    borderRadius: 8,
    backgroundColor: 'rgba(255,255,255,0.04)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  icon: { fontSize: 16 },
  dirBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 999,
    backgroundColor: 'rgba(141,208,167,0.08)',
    borderWidth: 1,
    borderColor: 'rgba(141,208,167,0.24)',
  },
  dirBadgeText: {
    color: colors.sage,
    fontSize: 9,
    fontFamily: fonts.sans,
  },
  fileName: {
    color: colors.text.primary,
    fontSize: 13,
    fontWeight: '500',
    fontFamily: fonts.sans,
    marginBottom: 4,
  },
  fileMeta: {
    color: colors.text.muted,
    fontSize: 10,
    fontFamily: fonts.mono,
  },
});
