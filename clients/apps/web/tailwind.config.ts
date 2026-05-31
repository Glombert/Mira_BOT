import type { Config } from 'tailwindcss';
// Дизайн-токены — единый источник (clients/packages/shared). Менять цвета/шрифты там.
import { palette, rawColor, alpha, fonts, radii } from '../../packages/shared/src/tokens';

const config: Config = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          base: palette.midnight,
          elevated: palette.surface,
          overlay: palette.abyss,
          input: palette.sidebar,
          card: palette.surface,
          sidebar: palette.sidebar,
          composer: rawColor.composer,
          page: palette.midnight,
          deep: palette.abyss,
        },
        text: {
          primary: palette.ink,
          secondary: alpha(palette.ink, 0.62),
          muted: alpha(palette.ink, 0.36),
          faint: alpha(palette.ink, 0.22),
          'on-accent': palette.midnight,
        },
        accent: {
          DEFAULT: palette.gold,
          hover: palette.goldHover,
          soft: alpha(palette.gold, 0.22),
          glow: alpha(palette.gold, 0.55),
          dim: alpha(palette.gold, 0.1),
          muted: alpha(palette.ink, 0.1),
          secondary: alpha(palette.ink, 0.62),
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
        success: palette.sage,
        warning: palette.gold,
        error: palette.rose,
        info: palette.mystic,
        border: {
          subtle: alpha(palette.ink, 0.1),
          DEFAULT: alpha(palette.ink, 0.1),
          strong: alpha(palette.gold, 0.3),
          focus: palette.gold,
          divider: alpha(palette.ink, 0.06),
        },
        bubble: {
          userBg: alpha(palette.gold, 0.1),
          userBorder: alpha(palette.gold, 0.32),
          miraBg: rawColor.bubbleMiraBg,
          miraBorder: alpha(palette.ink, 0.08),
        },
        status: {
          online: palette.sage,
          reconnecting: palette.gold,
          offline: palette.rose,
        },
      },
      fontFamily: {
        serif: [`"${fonts.serif}"`, 'Georgia', 'serif'],
        sans: [fonts.sans, 'system-ui', 'sans-serif'],
        mono: [`"${fonts.mono}"`, 'monospace'],
      },
      borderRadius: {
        bubble: `${radii.bubble}px`,
        card: `${radii.card}px`,
        pill: `${radii.pill}px`,
        button: `${radii.button}px`,
        input: `${radii.input}px`,
        'input-mobile': `${radii.inputMobile}px`,
        'sidebar-item': `${radii.sidebarItem}px`,
      },
      boxShadow: {
        soft: '0 2px 8px rgba(0, 0, 0, 0.3)',
        elevated: '0 8px 24px rgba(0, 0, 0, 0.4)',
        glow: '0 0 24px rgba(245, 188, 122, 0.18)',
        miraBubble: '0 8px 32px rgba(0, 0, 0, 0.35)',
        composer: '0 0 30px rgba(245, 188, 122, 0.04)',
        drawer: '12px 0 40px rgba(0, 0, 0, 0.45)',
      },
      transitionDuration: {
        fast: '120ms',
        normal: '200ms',
        slow: '320ms',
      },
      transitionTimingFunction: {
        mira: 'cubic-bezier(0.2, 0.0, 0.2, 1)',
      },
      animation: {
        'pulse-think': 'pulseThink 1.4s ease-in-out infinite',
        'fade-in-up': 'fadeInUp 200ms cubic-bezier(0.2, 0.0, 0.2, 1) forwards',
        'mira-breathe': 'miraBreathe 4.5s ease-in-out infinite',
        'mira-glow': 'miraGlow 5s ease-in-out infinite',
        'mira-twinkle': 'miraTwinkle 3s ease-in-out infinite',
        'mira-shimmer': 'miraShimmer 2.4s ease-in-out infinite',
        'mira-orbit': 'miraOrbit 60s linear infinite',
        'mira-rise': 'miraRise 0.6s ease-out both',
      },
      keyframes: {
        pulseThink: {
          '0%, 100%': { opacity: '0.4' },
          '50%': { opacity: '1' },
        },
        fadeInUp: {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        miraBreathe: {
          '0%, 100%': { opacity: '0.55', transform: 'scale(1)' },
          '50%': { opacity: '0.85', transform: 'scale(1.04)' },
        },
        miraGlow: {
          '0%, 100%': { filter: 'drop-shadow(0 0 12px rgba(245, 188, 122, 0.4))' },
          '50%': { filter: 'drop-shadow(0 0 24px rgba(245, 188, 122, 0.65))' },
        },
        miraTwinkle: {
          '0%, 100%': { opacity: '0.3' },
          '50%': { opacity: '1' },
        },
        miraShimmer: {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        miraOrbit: {
          from: { transform: 'rotate(0deg)' },
          to: { transform: 'rotate(360deg)' },
        },
        miraRise: {
          from: { transform: 'translateY(8px)', opacity: '0' },
          to: { transform: 'translateY(0)', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
};

export default config;
