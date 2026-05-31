import React from 'react';
import { TouchableOpacity, Text, StyleSheet, ActivityIndicator, type ViewStyle, type TextStyle } from 'react-native';
import { colors, spacing, radii, typography } from '../../theme';

type Variant = 'primary' | 'secondary' | 'ghost' | 'telegram';
type Size = 'sm' | 'md' | 'lg';

interface Props {
  title: string;
  onPress: () => void;
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  disabled?: boolean;
  style?: ViewStyle;
  textStyle?: TextStyle;
}

const sizeMap: Record<Size, { py: number; px: number; font: TextStyle }> = {
  sm: { py: 8, px: spacing.md, font: typography.body as TextStyle },
  md: { py: 12, px: spacing.xl, font: typography.body as TextStyle },
  lg: { py: 14, px: spacing['2xl'], font: typography.sidebarName as TextStyle },
};

export function Button({ title, onPress, variant = 'primary', size = 'md', loading, disabled, style, textStyle }: Props) {
  const s = sizeMap[size];
  const isDisabled = disabled || loading;

  return (
    <TouchableOpacity
      onPress={onPress}
      disabled={isDisabled}
      activeOpacity={0.8}
      style={[
        styles.base,
        { paddingVertical: s.py, paddingHorizontal: s.px, borderRadius: radii.button },
        styles[variant],
        isDisabled && styles.disabled,
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator size="small" color={variant === 'primary' ? colors.bg.page : colors.gold.DEFAULT} />
      ) : (
        <Text style={[s.font, styles.text, styles[`${variant}Text`], isDisabled && styles.disabledText, textStyle]}>
          {title}
        </Text>
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  base: {
    alignItems: 'center',
    justifyContent: 'center',
    minWidth: 80,
  },
  primary: {
    backgroundColor: colors.gold.DEFAULT,
  },
  secondary: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: colors.border.subtle,
  },
  ghost: {
    backgroundColor: 'transparent',
  },
  telegram: {
    backgroundColor: '#229ED9',
  },
  disabled: {
    opacity: 0.4,
  },
  text: {
    fontWeight: '700',
  },
  primaryText: {
    color: colors.bg.page,
  },
  secondaryText: {
    color: colors.gold.DEFAULT,
  },
  ghostText: {
    color: colors.text.muted,
  },
  telegramText: {
    color: '#fff',
  },
  disabledText: {
    color: colors.text.faint,
  },
});
