import React from 'react';
import { View, StyleSheet, type ViewProps } from 'react-native';
import { colors, spacing, radii, shadow } from '../../theme';

interface Props extends ViewProps {
  elevated?: boolean;
  padded?: boolean | 'sm' | 'md' | 'lg';
}

const padMap = {
  sm: spacing.md,
  md: spacing.lg,
  lg: spacing.xl,
};

export function Card({ children, elevated, padded = 'md', style, ...rest }: Props) {
  const pad = typeof padded === 'boolean' ? (padded ? spacing.lg : 0) : padMap[padded];
  return (
    <View
      style={[
        styles.base,
        { padding: pad, borderRadius: radii.card },
        elevated && shadow.miraBubble,
        style,
      ]}
      {...rest}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  base: {
    backgroundColor: colors.bg.surface,
    borderWidth: 1,
    borderColor: colors.border.subtle,
  },
});
