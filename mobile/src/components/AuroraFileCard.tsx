import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import type { Attachment } from '../types';
import { colors, spacing, radii, typography, fonts } from '../theme';

// Иконки типов файлов
const FILE_KIND_EMOJI: Record<string, string> = {
  pdf: '📄', doc: '📝', docx: '📝', xls: '📊', xlsx: '📊', csv: '📊',
  m4a: '🎙', mp3: '🎵', wav: '🎵', flac: '🎵',
  png: '🖼', jpg: '🖼', jpeg: '🖼', gif: '🖼', svg: '🖼', webp: '🖼',
  zip: '📦', tar: '📦', gz: '📦', rar: '📦',
  txt: '📃', md: '📃', json: '📃', xml: '📃', yaml: '📃', yml: '📃',
  py: '🐍', js: '📜', ts: '📜', tsx: '📜', jsx: '📜',
  ppt: '📽', pptx: '📽',
};

function fileEmoji(name: string): string {
  const ext = (name.split('.').pop() || '').toLowerCase();
  return FILE_KIND_EMOJI[ext] || '📎';
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

interface Props {
  file: Attachment;
  isCloud?: boolean;
  onPress?: (dir: string, name: string) => void;
  note?: string;
}

export function AuroraFileCard({ file, isCloud = false, onPress, note }: Props) {
  const handlePress = () => {
    if (onPress) onPress(file.dir, file.name);
  };

  return (
    <TouchableOpacity
      style={styles.card}
      onPress={handlePress}
      activeOpacity={0.7}
    >
      {/* Верх: иконка + локация */}
      <View style={styles.cardTop}>
        <View style={styles.fileIconWrap}>
          <Text style={styles.fileIcon}>{fileEmoji(file.name)}</Text>
        </View>
        {isCloud ? (
          <View style={styles.locBadge}>
            <Text style={styles.locBadgeText}>☁ облако</Text>
          </View>
        ) : null}
      </View>

      {/* Имя файла */}
      <Text style={styles.fileName} numberOfLines={1}>{file.name}</Text>

      {/* Размер */}
      <Text style={styles.fileMeta}>
        {file.size ? formatBytes(file.size) : ''}
        {file.dir ? ` · ${file.dir}/` : ''}
      </Text>

      {/* Заметка (из памяти Миры) */}
      {note ? (
        <Text style={styles.fileNote} numberOfLines={2}>{note}</Text>
      ) : null}
    </TouchableOpacity>
  );
}

export function AuroraFileGrid({
  files,
  isCloud = false,
  onFilePress,
}: {
  files: Attachment[];
  isCloud?: boolean;
  onFilePress?: (dir: string, name: string) => void;
}) {
  if (!files || files.length === 0) {
    return (
      <View style={styles.emptyWrap}>
        <Text style={styles.emptyText}>Нет файлов</Text>
      </View>
    );
  }

  return (
    <View style={styles.grid}>
      {files.map((f, i) => (
        <AuroraFileCard
          key={`${f.dir || ''}-${f.name}-${i}`}
          file={f}
          isCloud={isCloud}
          onPress={onFilePress}
        />
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.md,
    padding: spacing.md,
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
  fileIconWrap: {
    width: 32,
    height: 32,
    borderRadius: 8,
    backgroundColor: 'rgba(255,255,255,0.04)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  fileIcon: {
    fontSize: 16,
  },
  locBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 999,
    backgroundColor: 'rgba(141,208,167,0.10)',
    borderWidth: 1,
    borderColor: 'rgba(141,208,167,0.30)',
  },
  locBadgeText: {
    color: colors.sage,
    fontSize: 10,
    letterSpacing: 0.4,
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
    fontSize: 11,
    fontFamily: fonts.mono,
    marginBottom: 2,
  },
  fileNote: {
    color: colors.text.dim,
    fontSize: 12,
    fontFamily: fonts.serif,
    fontStyle: 'italic',
    marginTop: spacing.xs,
    lineHeight: 16,
  },
  emptyWrap: {
    padding: spacing['3xl'],
    alignItems: 'center' as const,
  },
  emptyText: {
    color: colors.text.faint,
    fontSize: typography.status.fontSize,
    fontFamily: fonts.sans,
  },
});
