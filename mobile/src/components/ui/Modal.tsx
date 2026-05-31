import React from 'react';
import {
  Modal as RNModal,
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  type ViewStyle,
} from 'react-native';
import { colors, spacing, radii, typography } from '../../theme';

interface Props {
  visible: boolean;
  title?: string;
  onClose: () => void;
  children: React.ReactNode;
  scrollable?: boolean;
  contentStyle?: ViewStyle;
}

export function Modal({ visible, title, onClose, children, scrollable, contentStyle }: Props) {
  const Body = scrollable ? ScrollView : View;
  return (
    <RNModal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={styles.card}>
          {!!title && (
            <View style={styles.header}>
              <Text style={styles.title}>{title}</Text>
              <TouchableOpacity onPress={onClose} style={styles.closeBtn}>
                <Text style={styles.closeText}>✕</Text>
              </TouchableOpacity>
            </View>
          )}
          <Body style={[styles.body, contentStyle]}>{children}</Body>
        </View>
      </View>
    </RNModal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: colors.bg.deep,
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.xl,
  },
  card: {
    width: '100%',
    maxHeight: '70%',
    backgroundColor: colors.bg.surface,
    borderRadius: radii.card,
    borderWidth: 1,
    borderColor: colors.border.subtle,
    padding: spacing.xl,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.md,
  },
  title: {
    color: colors.gold.DEFAULT,
    fontSize: typography.eventTitle.fontSize,
    fontWeight: typography.eventTitle.fontWeight,
  },
  closeBtn: {
    width: 32,
    height: 32,
    alignItems: 'center',
    justifyContent: 'center',
  },
  closeText: {
    color: colors.text.muted,
    fontSize: 20,
  },
  body: {
    maxHeight: 300,
  },
});
