import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet } from 'react-native';
import { Modal } from './ui/Modal';
import { colors, spacing, radii, typography } from '../theme';

interface Props {
  visible: boolean;
  cmd: string;
  label: string;
  placeholder: string;
  onSubmit: (cmdWithArgs: string) => void;
  onClose: () => void;
}

export function CommandFormModal({ visible, cmd, label, placeholder, onSubmit, onClose }: Props) {
  const [value, setValue] = useState('');

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed) return;
    onSubmit(`${cmd} ${trimmed}`);
    setValue('');
    onClose();
  };

  return (
    <Modal visible={visible} title={label} onClose={onClose}>
      <TextInput
        style={styles.input}
        value={value}
        onChangeText={setValue}
        placeholder={placeholder}
        placeholderTextColor={colors.text.faint}
        autoFocus
        multiline
        numberOfLines={3}
        textAlignVertical="top"
      />
      <TouchableOpacity style={styles.submitBtn} onPress={handleSubmit}>
        <Text style={styles.submitText}>Отправить</Text>
      </TouchableOpacity>
    </Modal>
  );
}

const styles = StyleSheet.create({
  input: {
    backgroundColor: colors.bg.deep,
    borderRadius: radii.sidebarItem,
    padding: spacing.md,
    color: colors.text.primary,
    fontSize: typography.body.fontSize,
    borderWidth: 1,
    borderColor: colors.border.subtle,
    minHeight: 80,
    marginBottom: spacing.md,
  },
  submitBtn: {
    backgroundColor: colors.gold.DEFAULT,
    borderRadius: radii.button,
    paddingVertical: spacing.md,
    alignItems: 'center',
  },
  submitText: {
    color: colors.bg.page,
    fontWeight: '700',
    fontSize: typography.body.fontSize,
  },
});
