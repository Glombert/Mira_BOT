import React, { useState, useCallback } from 'react';
import {
  View,
  TextInput,
  TouchableOpacity,
  Text,
  StyleSheet,
  ActivityIndicator,
  ScrollView,
  Alert,
} from 'react-native';
import { pick, errorCodes, isErrorWithCode } from '@react-native-documents/picker';
import { colors, typography, fonts, spacing, radii, shadow } from '../theme';
import { MiraIcon } from './ui/MiraIcon';

interface Props {
  onSend: (text: string) => void;
  onSendCommand?: (cmd: string) => void;
  onFileSelect?: (files: Array<{ uri: string; name: string; type: string }>) => void;
  pendingAttachments?: Array<{ name: string; size: number }>;
  onClearAttachment?: (index: number) => void;
  uploading?: boolean;
  disabled?: boolean;
}

export function AuroraComposer({
  onSend,
  onSendCommand,
  onFileSelect,
  pendingAttachments = [],
  onClearAttachment,
  uploading,
  disabled,
}: Props) {
  const [text, setText] = useState('');

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed && pendingAttachments.length === 0) return;
    if (disabled) return;
    if (trimmed.startsWith('/')) {
      onSendCommand?.(trimmed.slice(1));
    } else {
      onSend(trimmed);
    }
    setText('');
  }, [text, pendingAttachments, disabled, onSend, onSendCommand]);

  return (
    <View style={styles.container}>
      {pendingAttachments.length > 0 && (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.attachmentsRow}>
          {pendingAttachments.map((att, i) => (
            <View key={i} style={styles.attachmentChip}>
              <Text style={styles.attachmentText} numberOfLines={1}>
                📎 {att.name}
              </Text>
              <TouchableOpacity onPress={() => onClearAttachment?.(i)} style={styles.attachmentClear}>
                <Text style={styles.attachmentClearText}>×</Text>
              </TouchableOpacity>
            </View>
          ))}
        </ScrollView>
      )}

      <View style={styles.pill}>
        <TouchableOpacity
          onPress={async () => {
            if (!onFileSelect || disabled || uploading) return;
            try {
              const results = await pick({ allowMultiSelection: true, mode: 'open' });
              if (results && results.length > 0) {
                const files = results.map((r) => ({
                  uri: r.uri,
                  name: r.name ?? 'file',
                  type: r.type ?? 'application/octet-stream',
                }));
                onFileSelect(files);
              }
            } catch (e: unknown) {
              if (isErrorWithCode(e) && e.code === errorCodes.OPERATION_CANCELED) return;
              const msg = e instanceof Error ? e.message : 'Не удалось открыть файл';
              Alert.alert('Ошибка', msg);
            }
          }}
          style={styles.iconBtn}
          activeOpacity={0.8}
          disabled={uploading || disabled}
        >
          {uploading ? (
            <ActivityIndicator size="small" color={colors.gold.DEFAULT} />
          ) : (
            <MiraIcon name="paperclip" color={colors.text.dim} size={20} />
          )}
        </TouchableOpacity>

        <TextInput
          style={styles.input}
          value={text}
          onChangeText={setText}
          placeholder="напиши Мире · или просто помолчи рядом"
          placeholderTextColor={colors.text.dim}
          multiline
          maxLength={2000}
          editable={!disabled}
          onSubmitEditing={handleSend}
          returnKeyType="send"
        />

        <TouchableOpacity
          onPress={handleSend}
          style={[styles.sendBtn, text.trim().length === 0 && styles.sendBtnInactive]}
          activeOpacity={0.8}
          disabled={disabled || text.trim().length === 0}
        >
          <MiraIcon name="send" color={colors.bg.page} size={18} />
        </TouchableOpacity>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderTopWidth: 1,
    borderTopColor: colors.border.divider,
    backgroundColor: colors.bg.composer,
  },
  attachmentsRow: {
    flexDirection: 'row',
    marginBottom: spacing.sm,
  },
  attachmentChip: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(245,188,122,0.08)',
    borderWidth: 1,
    borderColor: colors.border.strong,
    borderRadius: radii.pill,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    marginRight: spacing.sm,
    gap: spacing.xs,
  },
  attachmentText: {
    ...typography.sidebarItem,
    color: colors.gold.DEFAULT,
    fontFamily: fonts.sans,
  },
  attachmentClear: {
    width: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: 'rgba(244,234,214,0.10)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  attachmentClearText: {
    color: colors.text.dim,
    fontSize: 12,
    lineHeight: 14,
  },
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(255,255,255,0.03)',
    borderWidth: 1,
    borderColor: colors.border.subtle,
    borderRadius: radii.inputMobile,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    ...shadow.composer,
  },
  iconBtn: {
    width: 32,
    height: 32,
    justifyContent: 'center',
    alignItems: 'center',
  },
  icon: {
    fontSize: 16,
    color: colors.text.dim,
  },
  input: {
    flex: 1,
    ...typography.composerPlaceholder,
    color: colors.text.primary,
    fontFamily: fonts.serif,
    maxHeight: 120,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.sm,
  },
  sendBtn: {
    width: 32,
    height: 32,
    borderRadius: radii.pill,
    backgroundColor: colors.gold.DEFAULT,
    justifyContent: 'center',
    alignItems: 'center',
    marginLeft: spacing.xs,
  },
  sendBtnInactive: {
    backgroundColor: 'rgba(245,188,122,0.20)',
  },
  sendIcon: {
    fontSize: 14,
    color: colors.bg.deep,
  },
});
