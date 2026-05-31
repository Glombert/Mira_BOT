import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { AuroraAvatar } from './ui/AuroraAvatar';
import { colors, typography, fonts, spacing, radii, shadow } from '../theme';

interface Props {
  children: React.ReactNode;
  time?: string;
  showAvatar?: boolean;
}

export function AuroraMiraBubble({ children, time, showAvatar = true }: Props) {
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
        {time && <Text style={styles.time}>{time}</Text>}
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
  time: {
    ...typography.timestamp,
    color: colors.text.muted,
    marginTop: 4,
  },
});
