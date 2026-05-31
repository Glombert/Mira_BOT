import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { colors, typography, fonts, spacing, radii } from '../theme';

interface Props {
  children: React.ReactNode;
  time?: string;
}

export function AuroraUserBubble({ children, time }: Props) {
  return (
    <View style={styles.wrapper}>
      <View style={styles.bubble}>
        {typeof children === 'string' ? (
          <Text style={styles.text}>{children}</Text>
        ) : (
          children
        )}
      </View>
      {time && <Text style={styles.time}>{time}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    alignSelf: 'flex-end',
    maxWidth: '72%',
    marginVertical: spacing.xs,
  },
  bubble: {
    backgroundColor: colors.bubble.userBg,
    borderWidth: 1,
    borderColor: colors.bubble.userBorder,
    borderRadius: radii.bubble,
    borderBottomRightRadius: 4,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  text: {
    ...typography.body,
    color: colors.text.primary,
    fontFamily: fonts.sans,
  },
  time: {
    ...typography.timestamp,
    color: colors.text.muted,
    alignSelf: 'flex-end',
    marginTop: 4,
  },
});
