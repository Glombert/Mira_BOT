import React, { useEffect, useRef } from 'react';
import { View, Text, Image, Animated, StyleSheet, TouchableOpacity } from 'react-native';
import { colors, typography, fonts, spacing, radii } from '../theme';
import { AuroraAvatar } from './ui/AuroraAvatar';

interface Props {
  userName?: string;
  chips?: string[];
  onChipPress?: (text: string) => void;
}

const DEFAULT_CHIPS = [
  'что сегодня важно?',
  'отложить всё до завтра',
  'просто посиди рядом',
];

export function AuroraWelcome({ userName = 'друг', chips = DEFAULT_CHIPS, onChipPress }: Props) {
  const rotate = useRef(new Animated.Value(0)).current;
  const breathe = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    const orbit = Animated.loop(
      Animated.timing(rotate, {
        toValue: 1,
        duration: 60000,
        useNativeDriver: true,
      })
    );
    orbit.start();

    const breath = Animated.loop(
      Animated.sequence([
        Animated.timing(breathe, { toValue: 1, duration: 2250, useNativeDriver: true }),
        Animated.timing(breathe, { toValue: 0, duration: 2250, useNativeDriver: true }),
      ])
    );
    breath.start();

    return () => {
      orbit.stop();
      breath.stop();
    };
  }, []);

  const spin = rotate.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '360deg'] });
  const glowOpacity = breathe.interpolate({ inputRange: [0, 1], outputRange: [0.4, 0.7] });
  const glowScale = breathe.interpolate({ inputRange: [0, 1], outputRange: [1, 1.05] });

  return (
    <View style={styles.container}>
      <View style={styles.portraitWrap}>
        <Animated.View style={[styles.orbitRing, { transform: [{ rotate: spin }] }]} />
        <Animated.View
          style={[
            styles.glow,
            {
              opacity: glowOpacity,
              transform: [{ scale: glowScale }],
            },
          ]}
        />
        <AuroraAvatar size={PORTRAIT_SIZE} glow={false} />
      </View>

      <Text style={styles.greeting}>
        Доброго вечера, <Text style={styles.greetingName}>{userName}</Text>
      </Text>

      <Text style={styles.prompt}>
        я перечитала наш утренний разговор. вернёмся к задачам или просто поговорим?
      </Text>

      <View style={styles.chips}>
        {chips.map((chip, i) => (
          <TouchableOpacity
            key={i}
            style={styles.chip}
            onPress={() => onChipPress?.(chip)}
            activeOpacity={0.8}
          >
            <Text style={styles.chipText}>{chip}</Text>
          </TouchableOpacity>
        ))}
      </View>

      <View style={styles.fadeLine} />
    </View>
  );
}

const PORTRAIT_SIZE = 96;

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingTop: spacing['4xl'],
    paddingBottom: spacing.lg,
  },
  portraitWrap: {
    width: PORTRAIT_SIZE,
    height: PORTRAIT_SIZE,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: spacing.xl,
  },
  orbitRing: {
    position: 'absolute',
    width: PORTRAIT_SIZE + 16,
    height: PORTRAIT_SIZE + 16,
    borderRadius: (PORTRAIT_SIZE + 16) / 2,
    borderWidth: 1,
    borderColor: colors.border.strong,
    borderStyle: 'dashed',
  },
  glow: {
    position: 'absolute',
    width: PORTRAIT_SIZE + 12,
    height: PORTRAIT_SIZE + 12,
    borderRadius: (PORTRAIT_SIZE + 12) / 2,
    backgroundColor: colors.gold.glow,
  },
  portrait: {
    width: PORTRAIT_SIZE,
    height: PORTRAIT_SIZE,
    borderRadius: PORTRAIT_SIZE / 2,
    borderWidth: 1,
    borderColor: colors.border.strong,
  },
  greeting: {
    ...typography.welcomeGreeting,
    color: colors.text.primary,
    fontFamily: fonts.serif,
    textAlign: 'center',
  },
  greetingName: {
    color: colors.gold.DEFAULT,
    fontFamily: fonts.serif,
  },
  prompt: {
    ...typography.welcomePrompt,
    color: colors.text.dim,
    fontFamily: fonts.serif,
    textAlign: 'center',
    maxWidth: 320,
    marginTop: spacing.sm,
  },
  chips: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    gap: spacing.sm,
    marginTop: spacing.lg,
  },
  chip: {
    height: 32,
    paddingHorizontal: spacing.md,
    borderRadius: radii.pill,
    borderWidth: 1,
    borderColor: colors.border.subtle,
    backgroundColor: 'rgba(255,255,255,0.02)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  chipText: {
    fontFamily: fonts.sans,
    fontSize: 12,
    color: colors.text.dim,
  },
  fadeLine: {
    width: 80,
    height: 1,
    marginTop: spacing.xl,
    backgroundColor: colors.gold.DEFAULT,
    opacity: 0.3,
  },
});
