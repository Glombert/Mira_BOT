import React from 'react';
import { TextInput, View, Text, StyleSheet, type TextInputProps } from 'react-native';
import { colors, spacing, radii, typography } from '../../theme';

interface Props extends TextInputProps {
  label?: string;
  hint?: string;
  error?: string;
}

export function Input({ label, hint, error, style, ...rest }: Props) {
  return (
    <View style={styles.wrapper}>
      {!!label && <Text style={styles.label}>{label}</Text>}
      <TextInput
        placeholderTextColor={colors.text.faint}
        {...rest}
        style={[
          styles.input,
          !!error && styles.inputError,
          style,
        ]}
      />
      {!!error && <Text style={styles.error}>{error}</Text>}
      {!!hint && !error && <Text style={styles.hint}>{hint}</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: { width: '100%' },
  label: {
    color: colors.text.dim,
    fontSize: typography.body.fontSize,
    marginBottom: spacing.xs,
  },
  input: {
    backgroundColor: colors.bg.page,
    borderRadius: radii.sidebarItem,
    padding: spacing.md,
    color: colors.text.primary,
    fontSize: typography.body.fontSize,
    borderWidth: 1,
    borderColor: colors.border.subtle,
    textAlignVertical: 'top',
  },
  inputError: {
    borderColor: colors.rose,
  },
  error: {
    color: colors.rose,
    fontSize: typography.status.fontSize,
    marginTop: spacing.xs,
  },
  hint: {
    color: colors.text.dim,
    fontSize: typography.status.fontSize,
    marginTop: spacing.xs,
  },
});
