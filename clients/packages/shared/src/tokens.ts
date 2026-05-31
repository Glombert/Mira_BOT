// Aurora Design System — единый источник дизайн-токенов.
//
// ЕДИНСТВЕННОЕ место, где живут цвета/шрифты/радиусы/отступы Миры.
// Потребляют: web (apps/web/tailwind.config.ts) и mobile (mobile/src/theme).
// Менять палитру/шрифт — только здесь. Источник вдохновения — aurora.jsx (Claude Designer).

/** Базовые цвета (hex). Прозрачные варианты — через alpha(). */
export const palette = {
  midnight: '#0b1226', // bg page / base
  abyss: '#070c1c', // bg deep / overlay
  surface: '#101a30', // bg surface / elevated / card
  sidebar: '#080d1d', // bg sidebar / input
  ink: '#f4ead6', // основной текст
  gold: '#f5bc7a',
  goldHover: '#f8cfa0',
  mystic: '#b9a3ff',
  sage: '#8dd0a7',
  rose: '#e88a8a',
} as const;

/** rgba-литералы, которые не выводятся из palette (одноразовые оттенки). */
export const rawColor = {
  composer: 'rgba(13, 21, 42, 0.88)',
  bubbleMiraBg: 'rgba(20, 30, 55, 0.85)',
} as const;

/** hex → rgba(r,g,b,a). Поддерживает #rgb и #rrggbb. */
export function alpha(hex: string, a: number): string {
  let h = hex.replace('#', '');
  if (h.length === 3) h = h.split('').map((c) => c + c).join('');
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${a})`;
}

export const fonts = {
  serif: 'Cormorant Garamond',
  sans: 'Manrope',
  mono: 'JetBrains Mono',
} as const;

export const radii = {
  bubble: 16,
  card: 12,
  pill: 999,
  button: 10,
  input: 18,
  inputMobile: 22,
  sidebarItem: 8,
} as const;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 18,
  '2xl': 22,
  '3xl': 28,
  '4xl': 36,
} as const;

export const duration = {
  fast: 120,
  normal: 200,
  slow: 320,
} as const;
