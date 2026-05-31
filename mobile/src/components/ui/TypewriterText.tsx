import React, { useState, useEffect, useRef, useCallback } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import Markdown from 'react-native-markdown-display';
import { colors, typography, radii, spacing } from '../../theme';

interface Props {
  content: string;
  isNew: boolean;
  speed?: number; // chars per second
  onComplete?: () => void;
}

const mdStyles = {
  body: { color: colors.text.primary, fontSize: typography.body.fontSize },
  paragraph: { color: colors.text.primary, fontSize: typography.body.fontSize, marginBottom: spacing.sm },
  link: { color: colors.gold.DEFAULT, textDecorationLine: 'underline' as const },
  strong: { color: colors.text.dim, fontWeight: '700' as const },
  em: { color: colors.text.dim, fontStyle: 'italic' as const },
  code_inline: {
    backgroundColor: colors.bg.deep,
    color: colors.text.dim,
    fontFamily: 'monospace',
    paddingHorizontal: 4,
    borderRadius: radii.sidebarItem,
  },
  fence: {
    backgroundColor: colors.bg.deep,
    color: colors.text.dim,
    fontFamily: 'monospace',
    padding: spacing.md,
    borderRadius: radii.sidebarItem,
    marginVertical: spacing.sm,
  },
  bullet_list: { marginLeft: spacing.sm },
  ordered_list: { marginLeft: spacing.sm },
  list_item: { marginBottom: spacing.xs },
};

// Выделяемый текст в Markdown (long-press → нативные маркеры → «Копировать»).
const mdSelectableRules = {
  textgroup: (node: any, children: React.ReactNode, _parent: any, styles: any) => (
    <Text key={node.key} style={styles.textgroup} selectable>
      {children}
    </Text>
  ),
};

export function TypewriterText({ content, isNew, speed = 30, onComplete }: Props) {
  const [displayed, setDisplayed] = useState(isNew ? '' : content);
  const [done, setDone] = useState(!isNew);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!isNew) {
      setDisplayed(content);
      setDone(true);
      return;
    }
    setDisplayed('');
    setDone(false);
    let idx = 0;
    const total = content.length;
    const msPerChar = Math.max(16, Math.floor(1000 / speed));

    intervalRef.current = setInterval(() => {
      idx += 1;
      if (idx >= total) {
        setDisplayed(content);
        setDone(true);
        if (intervalRef.current) clearInterval(intervalRef.current);
        onComplete?.();
      } else {
        setDisplayed(content.slice(0, idx));
      }
    }, msPerChar);

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [content, isNew, speed, onComplete]);

  const skip = useCallback(() => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    setDisplayed(content);
    setDone(true);
    onComplete?.();
  }, [content, onComplete]);

  if (!isNew || done) {
    return (
      <Markdown style={mdStyles} rules={mdSelectableRules}>
        {content || ''}
      </Markdown>
    );
  }

  return (
    <TouchableOpacity activeOpacity={0.9} onPress={skip}>
      <Text style={styles.typingText}>{displayed}</Text>
      <View style={styles.cursor} />
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  typingText: {
    color: colors.text.primary,
    fontSize: typography.body.fontSize,
    lineHeight: typography.body.lineHeight,
  },
  cursor: {
    width: 2,
    height: 16,
    backgroundColor: colors.gold.DEFAULT,
    marginTop: 2,
  },
});
