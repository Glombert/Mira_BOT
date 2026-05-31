// Aurora Design System — Mira UI tokens (мобайл).
// Цвета/шрифты/радиусы/отступы берутся из ОБЩЕГО источника @mira/shared/tokens
// (монорепо clients/packages/shared), чтобы веб и мобайл не расходились.
// Платформенные части (RN-typography, RN-shadow) остаются здесь.

import {
  palette,
  rawColor,
  alpha,
  fonts as sharedFonts,
  radii as sharedRadii,
  spacing as sharedSpacing,
} from '@mira/shared/tokens';

export const fonts = sharedFonts;

export const colors = {
  bg: {
    page: palette.midnight,
    deep: palette.abyss,
    surface: palette.surface,
    sidebar: palette.sidebar,
    composer: rawColor.composer,
  },
  text: {
    primary: palette.ink,
    dim: alpha(palette.ink, 0.62),
    muted: alpha(palette.ink, 0.36),
    faint: alpha(palette.ink, 0.22),
  },
  gold: {
    DEFAULT: palette.gold,
    soft: alpha(palette.gold, 0.22),
    glow: alpha(palette.gold, 0.55),
    dim: alpha(palette.gold, 0.1),
  },
  mystic: {
    DEFAULT: palette.mystic,
    soft: alpha(palette.mystic, 0.2),
  },
  sage: palette.sage,
  rose: palette.rose,
  border: {
    subtle: alpha(palette.ink, 0.1),
    strong: alpha(palette.gold, 0.3),
    divider: alpha(palette.ink, 0.06),
  },
  bubble: {
    userBg: alpha(palette.gold, 0.1),
    userBorder: alpha(palette.gold, 0.32),
    miraBg: rawColor.bubbleMiraBg,
    miraBorder: alpha(palette.ink, 0.08),
  },
} as const;

export const spacing = sharedSpacing;

export const radii = sharedRadii;

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
    shadowColor: alpha(palette.gold, 0.04),
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
