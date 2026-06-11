import React from 'react';
import { View, Text, StyleSheet, TouchableOpacity, Platform, ToastAndroid } from 'react-native';
import Clipboard from '@react-native-clipboard/clipboard';
import { AuroraAvatar } from './ui/AuroraAvatar';
import { colors, typography, fonts, spacing, radii, shadow } from '../theme';

interface Props {
  children: React.ReactNode;
  time?: string;
  showAvatar?: boolean;
  // Весь текст ответа — для кнопки «копировать». В RN выделение не тянется
  // через несколько абзацев (каждый — отдельный <Text>), поэтому копируем
  // весь пузырь одним тапом.
  copyText?: string;
}

export function AuroraMiraBubble({ children, time, showAvatar = true, copyText }: Props) {
  const onCopy = () => {
    if (!copyText) return;
    Clipboard.setString(copyText);
    if (Platform.OS === 'android') ToastAndroid.show('Скопировано', ToastAndroid.SHORT);
  };

  return (
    <View style={styles.row}>
      {showAvatar && (
        <AuroraAvatar size={36} glow={false} borderColor={colors.border.subtle} />
      )}
      <View style={styles.content}>
        <View style={styles.bubble}>
          <View style={styles.goldLine} />
          <View style={styles.inner}>
            {typeof children === 'string' ? (
              <Text style={styles.text}>{children}</Text>
            ) : (
              children
            )}
          </View>
        </View>
        <View style={styles.footer}>
          {time && <Text style={styles.time}>{time}</Text>}
          {copyText ? (
            <TouchableOpacity onPress={onCopy} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }} activeOpacity={0.6}>
              <Text style={styles.copyBtn}>⧉ копировать</Text>
            </TouchableOpacity>
          ) : null}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.sm,
    maxWidth: '82%',
    marginVertical: spacing.xs,
  },
  content: {
    flex: 1,
  },
  bubble: {
    flexDirection: 'row',
    backgroundColor: colors.bubble.miraBg,
    borderWidth: 1,
    borderColor: colors.bubble.miraBorder,
    borderRadius: radii.bubble,
    borderBottomLeftRadius: 4,
    overflow: 'hidden',
    ...shadow.miraBubble,
  },
  goldLine: {
    width: 2,
    backgroundColor: colors.gold.DEFAULT,
    opacity: 0.5,
  },
  inner: {
    flex: 1,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  text: {
    ...typography.miraReply,
    color: colors.text.primary,
    fontFamily: fonts.serif,
  },
  footer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    marginTop: 4,
  },
  time: {
    ...typography.timestamp,
    color: colors.text.muted,
  },
  copyBtn: {
    ...typography.timestamp,
    color: colors.text.muted,
    fontFamily: fonts.mono,
  },
});
