import React from 'react';
import { View } from 'react-native';
import Svg, { Defs, LinearGradient, Stop, Path, Circle } from 'react-native-svg';

/** Мини-график area-стиля (как AreaChart в веб-клиенте). */
export function Sparkline({
  data,
  height = 90,
  color = '#f5bc7a',
}: {
  data: number[];
  height?: number;
  color?: string;
}) {
  const w = 320;
  const safe = data.length >= 2 ? data : [0, 0];
  const max = Math.max(...safe, 0.001) * 1.15;
  const stepX = w / (safe.length - 1);
  const y = (v: number) => height - (v / max) * height;
  const pts = safe.map((v, i) => `${i * stepX},${y(v)}`);
  const line = `M ${pts.join(' L ')}`;
  const area = `${line} L ${w},${height} L 0,${height} Z`;
  const gid = `sg-${color.replace(/[^a-z0-9]/gi, '')}`;
  return (
    <View style={{ width: '100%' }}>
      <Svg width="100%" height={height} viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none">
        <Defs>
          <LinearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
            <Stop offset="0" stopColor={color} stopOpacity="0.28" />
            <Stop offset="1" stopColor={color} stopOpacity="0" />
          </LinearGradient>
        </Defs>
        <Path d={area} fill={`url(#${gid})`} />
        <Path d={line} fill="none" stroke={color} strokeWidth={1.6} strokeLinejoin="round" />
        <Circle cx={(safe.length - 1) * stepX} cy={y(safe[safe.length - 1])} r={3.5} fill={color} />
      </Svg>
    </View>
  );
}
