import React from 'react';
import { View } from 'react-native';
import Svg, { Defs, LinearGradient, Stop, Path, Line, Text as SvgText } from 'react-native-svg';

type Slot = { ts: string; users: Record<string, number> };
type LineDef = { name: string; color: string };

/** Мультилинейный график трафика: линия на каждое устройство своим цветом,
 *  оси время × объём, сетка, лёгкая заливка (Grafana-стиль). */
export function MultiLineChart({ series, lines, height = 150 }: {
  series: Slot[]; lines: LineDef[]; height?: number;
}) {
  const w = 600;
  const n = series.length;
  let max = 0;
  for (const s of series) for (const l of lines) max = Math.max(max, s.users[l.name] || 0);
  max = max * 1.15 || 1;
  const stepX = n > 1 ? w / (n - 1) : 0;
  const x = (i: number) => i * stepX;
  const y = (v: number) => height - (v / max) * height;
  const yTicks = [0, max / 2, max];
  const fmt = (mb: number) => (mb >= 1024 ? `${(mb / 1024).toFixed(1)}G` : `${Math.round(mb)}M`);

  return (
    <View style={{ width: '100%' }}>
      <Svg width="100%" height={height} viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none">
        <Defs>
          {lines.map((l, i) => (
            <LinearGradient key={i} id={`mlfill-${i}`} x1="0" y1="0" x2="0" y2="1">
              <Stop offset="0" stopColor={l.color} stopOpacity="0.18" />
              <Stop offset="1" stopColor={l.color} stopOpacity="0" />
            </LinearGradient>
          ))}
        </Defs>
        {yTicks.map((t, i) => (
          <React.Fragment key={i}>
            <Line x1={0} y1={y(t)} x2={w} y2={y(t)} stroke="rgba(244,234,214,0.07)" strokeWidth={1} />
            <SvgText x={2} y={y(t) - 3} fill="rgba(244,234,214,0.35)" fontSize={10} fontFamily="monospace">{fmt(t)}</SvgText>
          </React.Fragment>
        ))}
        {n >= 2 && lines.map((l, li) => {
          const pts = series.map((s, i) => `${x(i)},${y(s.users[l.name] || 0)}`);
          const line = `M ${pts.join(' L ')}`;
          const area = `${line} L ${x(n - 1)},${height} L 0,${height} Z`;
          return (
            <React.Fragment key={li}>
              <Path d={area} fill={`url(#mlfill-${li})`} />
              <Path d={line} fill="none" stroke={l.color} strokeWidth={1.6} strokeLinejoin="round" />
            </React.Fragment>
          );
        })}
      </Svg>
    </View>
  );
}
