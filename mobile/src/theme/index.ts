// Aurora Design System — Mira UI tokens
// Colors: midnight blue + amber gold mystic
// Fonts: Cormorant Garamond (serif), Manrope (sans), JetBrains Mono (mono)

export const fonts = {
  serif: 'Cormorant Garamond',
  sans: 'Manrope',
  mono: 'JetBrains Mono',
} as const;

export const colors = {
  bg: {
    page: '#0b1226',
    deep: '#070c1c',
    surface: '#101a30',
    sidebar: '#080d1d',
    composer: 'rgba(13, 21, 42, 0.88)',
  },
  text: {
    primary: '#f4ead6',
    dim: 'rgba(244, 234, 214, 0.62)',
    muted: 'rgba(244, 234, 214, 0.36)',
    faint: 'rgba(244, 234, 214, 0.22)',
  },
  gold: {
    DEFAULT: '#f5bc7a',
    soft: 'rgba(245, 188, 122, 0.22)',
    glow: 'rgba(245, 188, 122, 0.55)',
    dim: 'rgba(245, 188, 122, 0.10)',
  },
  mystic: {
    DEFAULT: '#b9a3ff',
    soft: 'rgba(185, 163, 255, 0.20)',
  },
  sage: '#8dd0a7',
  rose: '#e88a8a',
  border: {
    subtle: 'rgba(244, 234, 214, 0.10)',
    strong: 'rgba(245, 188, 122, 0.30)',
    divider: 'rgba(244, 234, 214, 0.06)',
  },
  bubble: {
    userBg: 'rgba(245, 188, 122, 0.10)',
    userBorder: 'rgba(245, 188, 122, 0.32)',
    miraBg: 'rgba(20, 30, 55, 0.85)',
    miraBorder: 'rgba(244, 234, 214, 0.08)',
  },
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

export const radii = {
  bubble: 16,
  card: 12,
  pill: 999,
  button: 10,
  input: 18,
  inputMobile: 22,
  sidebarItem: 8,
} as const;

export const typography = {
  topbarName: { fontFamily: fonts.serif, fontSize: 23, lineHeight: 26, fontWeight: '500' as const, letterSpacing: 0.01 },
  sidebarName: { fontFamily: fonts.serif, fontSize: 19, lineHeight: 22, fontWeight: '400' as const, letterSpacing: 0.01 },
  welcomeGreeting: { fontFamily: fonts.serif, fontSize: 32, lineHeight: 38, fontWeight: '400' as const, letterSpacing: 0.01, fontStyle: 'italic' as const },
  welcomePrompt: { fontFamily: fonts.serif, fontSize: 18, lineHeight: 24, fontWeight: '400' as const, fontStyle: 'italic' as const },
  body: { fontFamily: fonts.sans, fontSize: 14, lineHeight: 20, fontWeight: '400' as const },
  miraReply: { fontFamily: fonts.serif, fontSize: 14.5, lineHeight: 21, fontWeight: '400' as const },
  sidebarItem: { fontFamily: fonts.sans, fontSize: 13, lineHeight: 18, fontWeight: '400' as const },
  sectionLabel: { fontFamily: fonts.sans, fontSize: 10, lineHeight: 12, fontWeight: '600' as const, letterSpacing: 2.2 },
  status: { fontFamily: fonts.sans, fontSize: 11, lineHeight: 14, fontWeight: '400' as const, letterSpacing: 0.88 },
  timestamp: { fontFamily: fonts.mono, fontSize: 10, lineHeight: 12, fontWeight: '400' as const, letterSpacing: 0.6 },
  composerPlaceholder: { fontFamily: fonts.serif, fontSize: 14, lineHeight: 20, fontWeight: '400' as const, fontStyle: 'italic' as const },
  composerHints: { fontFamily: fonts.sans, fontSize: 10, lineHeight: 12, fontWeight: '400' as const, letterSpacing: 0.8 },
  monoHint: { fontFamily: fonts.mono, fontSize: 10, lineHeight: 12, fontWeight: '400' as const },
  thinkingSteps: { fontFamily: fonts.mono, fontSize: 11.5, lineHeight: 16, fontWeight: '400' as const },
  memoryFact: { fontFamily: fonts.serif, fontSize: 14, lineHeight: 20, fontWeight: '400' as const, fontStyle: 'italic' as const },
  eventTitle: { fontFamily: fonts.serif, fontSize: 16, lineHeight: 22, fontWeight: '500' as const },
  eventTime: { fontFamily: fonts.mono, fontSize: 12, lineHeight: 16, fontWeight: '400' as const, letterSpacing: 0.24 },
  reactionChip: { fontFamily: fonts.sans, fontSize: 11, lineHeight: 14, fontWeight: '400' as const, letterSpacing: 0.44 },
  version: { fontFamily: fonts.mono, fontSize: 11, lineHeight: 14, fontWeight: '400' as const },
} as const;

export const shadow = {
  miraBubble: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.25,
    shadowRadius: 24,
    elevation: 8,
  },
  composer: {
    shadowColor: 'rgba(245, 188, 122, 0.04)',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 1,
    shadowRadius: 30,
    elevation: 4,
  },
  drawer: {
    shadowColor: '#000',
    shadowOffset: { width: 12, height: 0 },
    shadowOpacity: 0.45,
    shadowRadius: 40,
    elevation: 16,
  },
} as const;

export const theme = {
  fonts,
  colors,
  spacing,
  radii,
  typography,
  shadow,
} as const;
