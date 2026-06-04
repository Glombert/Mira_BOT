import React, { useEffect, useRef } from 'react';
import { View, Text, Animated, StyleSheet, Easing } from 'react-native';
import { colors, spacing, typography, fonts } from '../theme';

/**
 * AuroraThinkingRing — золотое дыхательное кольцо «Мира думает».
 * Анимация: pulse (scale 1 → 1.15), rotate (360° за 3с), opaity-пульсация.
 * Композиция: кольцо → золотые точки-частицы → надпись «думает».
 */
export function AuroraThinkingRing() {
  const pulse = useRef(new Animated.Value(1)).current;
  const rotate = useRef(new Animated.Value(0)).current;
  const dot1 = useRef(new Animated.Value(0.4)).current;
  const dot2 = useRef(new Animated.Value(0.4)).current;
  const dot3 = useRef(new Animated.Value(0.4)).current;

  useEffect(() => {
    // Pulse loop
    const pulseLoop = Animated.loop(
      Animated.sequence([
        Animated.timing(pulse, {
          toValue: 1.15,
          duration: 1400,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
        Animated.timing(pulse, {
          toValue: 1,
          duration: 1400,
          easing: Easing.inOut(Easing.ease),
          useNativeDriver: true,
        }),
      ])
    );
    pulseLoop.start();

    // Rotate loop
    const rotateLoop = Animated.loop(
      Animated.timing(rotate, {
        toValue: 1,
        duration: 3000,
        easing: Easing.linear,
        useNativeDriver: true,
      })
    );
    rotateLoop.start();

    // Dots: staggered opacity (sequential blink)
    const makeDot = (dot: Animated.Value, delay: number) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(delay),
          Animated.timing(dot, {
            toValue: 1,
            duration: 400,
            useNativeDriver: true,
          }),
          Animated.timing(dot, {
            toValue: 0.4,
            duration: 400,
            useNativeDriver: true,
          }),
        ])
      );

    makeDot(dot1, 0).start();
    makeDot(dot2, 200).start();
    makeDot(dot3, 400).start();

    return () => {
      pulseLoop.stop();
      rotateLoop.stop();
    };
  }, [pulse, rotate, dot1, dot2, dot3]);

  const spin = rotate.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', '360deg'],
  });

  return (
    <View style={styles.wrap}>
      {/* Pulse ring */}
      <Animated.View
        style={[
          styles.ring,
          {
            transform: [{ scale: pulse }, { rotate: spin }],
          },
        ]}
      >
        <View style={styles.ringDot} />
        <View style={[styles.ringDot, { top: -1, right: 10 }]} />
        <View style={[styles.ringDot, { bottom: -1, left: 10 }]} />
      </Animated.View>

      {/* Center text */}
      <View style={styles.textWrap}>
        <Text style={styles.label}>Мира</Text>
        <View style={styles.dotsRow}>
          <Animated.Text style={[styles.dot, { opacity: dot1 }]}>·</Animated.Text>
          <Animated.Text style={[styles.dot, { opacity: dot2 }]}>·</Animated.Text>
          <Animated.Text style={[styles.dot, { opacity: dot3 }]}>·</Animated.Text>
        </View>
        <Text style={styles.sublabel}>думает</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    alignSelf: 'center',
    alignItems: 'center',
    justifyContent: 'center',
    width: 90,
    height: 90,
    marginVertical: spacing['2xl'],
  },
  ring: {
    position: 'absolute',
    width: 56,
    height: 56,
    borderRadius: 28,
    borderWidth: 1,
    borderColor: 'rgba(245, 188, 122, 0.35)',
  },
  ringDot: {
    position: 'absolute',
    width: 4,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.gold.DEFAULT,
  },
  textWrap: {
    alignItems: 'center',
  },
  label: {
    color: colors.text.dim,
    fontSize: typography.status.fontSize,
    fontFamily: fonts.serif,
    fontStyle: 'italic',
  },
  sublabel: {
    color: colors.text.muted,
    fontSize: 11,
    fontFamily: fonts.sans,
    marginTop: 2,
  },
  dotsRow: {
    flexDirection: 'row',
    gap: 5,
    marginTop: 2,
    marginBottom: 2,
  },
  dot: {
    color: colors.gold.DEFAULT,
    fontSize: 22,
    lineHeight: 22,
  },
});
