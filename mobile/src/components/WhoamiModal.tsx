import React from 'react';
import { Text } from 'react-native';
import { Modal } from './ui/Modal';
import { colors, typography } from '../theme';

interface Props {
  visible: boolean;
  content: string;
  onClose: () => void;
}

export function WhoamiModal({ visible, content, onClose }: Props) {
  const lines = content.split('\n').filter(Boolean);

  return (
    <Modal visible={visible} title="Профиль" onClose={onClose} scrollable>
      {lines.map((line, i) => (
        <Text key={i} style={{ color: colors.text.primary, fontSize: typography.body.fontSize, marginBottom: 8 }}>
          {line}
        </Text>
      ))}
    </Modal>
  );
}
