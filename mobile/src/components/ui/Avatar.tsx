import React from 'react';
import { View, Image, Text, StyleSheet } from 'react-native';
import { colors, radii } from '../../theme';

interface Props {
  source?: { uri: string } | number;
  size?: number;
  fallback?: string;
  border?: boolean;
}

export function Avatar({ source, size = 40, fallback = 'М', border }: Props) {
  const hasImage = !!source;
  return (
    <View
      style={[
        styles.container,
        {
          width: size,
          height: size,
          borderRadius: size / 2,
          borderWidth: border ? 1.5 : 0,
        },
      ]}
    >
      {hasImage ? (
        <Image source={source} style={{ width: size, height: size, borderRadius: size / 2 }} />
      ) : (
        <Text style={[styles.fallback, { fontSize: size * 0.45 }]}>{fallback[0]}</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: colors.bg.deep,
    borderColor: colors.gold.glow,
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  },
  fallback: {
    color: colors.gold.DEFAULT,
    fontWeight: '700',
  },
});
