import { Animated, Easing } from 'react-native';

// ── Aurora animations ─────────────────────────────────────────

export function createBreatheAnimation(value: Animated.Value, duration = 4500) {
  return Animated.loop(
    Animated.sequence([
      Animated.timing(value, {
        toValue: 1,
        duration: duration / 2,
        easing: Easing.inOut(Easing.ease),
        useNativeDriver: true,
      }),
      Animated.timing(value, {
        toValue: 0,
        duration: duration / 2,
        easing: Easing.inOut(Easing.ease),
        useNativeDriver: true,
      }),
    ])
  );
}

export function createTwinkleAnimation(value: Animated.Value, duration = 3000) {
  return Animated.loop(
    Animated.sequence([
      Animated.timing(value, {
        toValue: 1,
        duration: duration / 2,
        easing: Easing.inOut(Easing.ease),
        useNativeDriver: true,
      }),
      Animated.timing(value, {
        toValue: 0,
        duration: duration / 2,
        easing: Easing.inOut(Easing.ease),
        useNativeDriver: true,
      }),
    ])
  );
}

export function createShimmerAnimation(translateX: Animated.Value, duration = 2400) {
  return Animated.loop(
    Animated.timing(translateX, {
      toValue: 1,
      duration,
      easing: Easing.inOut(Easing.ease),
      useNativeDriver: true,
    })
  );
}

export function createBlinkAnimation(value: Animated.Value, duration = 1300) {
  return Animated.loop(
    Animated.sequence([
      Animated.timing(value, {
        toValue: 1,
        duration: duration * 0.35,
        easing: Easing.inOut(Easing.ease),
        useNativeDriver: true,
      }),
      Animated.timing(value, {
        toValue: 0,
        duration: duration * 0.35,
        easing: Easing.inOut(Easing.ease),
        useNativeDriver: true,
      }),
      Animated.timing(value, {
        toValue: 0,
        duration: duration * 0.30,
        easing: Easing.linear,
        useNativeDriver: true,
      }),
    ])
  );
}

export function createOrbitAnimation(rotate: Animated.Value, duration = 60000) {
  return Animated.loop(
    Animated.timing(rotate, {
      toValue: 1,
      duration,
      easing: Easing.linear,
      useNativeDriver: true,
    })
  );
}

export function createRiseAnimation(
  translateY: Animated.Value,
  opacity: Animated.Value,
  duration = 600
) {
  return Animated.parallel([
    Animated.timing(translateY, {
      toValue: 0,
      duration,
      easing: Easing.out(Easing.ease),
      useNativeDriver: true,
    }),
    Animated.timing(opacity, {
      toValue: 1,
      duration,
      easing: Easing.out(Easing.ease),
      useNativeDriver: true,
    }),
  ]);
}

// ── Pre-built animated values (for simple usage) ──────────────

export function useBreatheValue() {
  const value = new Animated.Value(0);
  createBreatheAnimation(value).start();
  return value;
}

export function useTwinkleValue() {
  const value = new Animated.Value(0);
  createTwinkleAnimation(value).start();
  return value;
}

export function useOrbitValue() {
  const value = new Animated.Value(0);
  createOrbitAnimation(value).start();
  return value;
}
