import React, { useEffect, useRef } from 'react';
import { View, Image, Animated, StyleSheet } from 'react-native';
import { colors, fonts } from '../../theme';

interface Props {
  size?: number;
  glow?: boolean;
  glowColor?: string;
  borderColor?: string;
  source?: any;
}

export function AuroraAvatar({
  size = 40,
  glow = true,
  glowColor = colors.gold.glow,
  borderColor = colors.border.strong,
  source = require('../../assets/mira-portrait.png'),
}: Props) {
  const breathe = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    if (!glow) return;
    const anim = Animated.loop(
      Animated.sequence([
        Animated.timing(breathe, {
          toValue: 1,
          duration: 2250,
          useNativeDriver: true,
        }),
        Animated.timing(breathe, {
          toValue: 0,
          duration: 2250,
          useNativeDriver: true,
        }),
      ])
    );
    anim.start();
    return () => anim.stop();
  }, [glow]);

  const glowScale = breathe.interpolate({
    inputRange: [0, 1],
    outputRange: [1, 1.08],
  });
  const glowOpacity = breathe.interpolate({
    inputRange: [0, 1],
    outputRange: [0.18, 0.32],
  });

  // Halo лишь чуть выходит за круг — мягкое свечение, а не толстая «рамка».
  const haloSize = size * 1.1;

  return (
    <View style={[styles.container, { width: size, height: size }]}>
      {glow && (
        <Animated.View
          style={[
            styles.halo,
            {
              width: haloSize,
              height: haloSize,
              borderRadius: haloSize / 2,
              backgroundColor: glowColor,
              opacity: glowOpacity,
              transform: [{ scale: glowScale }],
            },
          ]}
        />
      )}
      <View
        style={[
          styles.imageWrap,
          { width: size, height: size, borderRadius: size / 2, borderColor },
        ]}
      >
        <Image
          source={source}
          resizeMode="cover"
          style={{
            width: size * 1.18,
            height: size * 1.18,
            marginLeft: -size * 0.09,
            marginTop: -size * 0.09,
          }}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    justifyContent: 'center',
    alignItems: 'center',
  },
  halo: {
    position: 'absolute',
  },
  imageWrap: {
    borderWidth: 1,
    backgroundColor: '#1a1f2e',
    overflow: 'hidden',
  },
});
