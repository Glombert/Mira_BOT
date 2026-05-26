import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          base: '#0b1226',
          elevated: '#101a30',
          overlay: '#070c1c',
          input: '#080d1d',
          card: '#101a30',
          sidebar: '#080d1d',
          composer: 'rgba(13, 21, 42, 0.88)',
          page: '#0b1226',
          deep: '#070c1c',
        },
        text: {
          primary: '#f4ead6',
          secondary: 'rgba(244, 234, 214, 0.62)',
          muted: 'rgba(244, 234, 214, 0.36)',
          faint: 'rgba(244, 234, 214, 0.22)',
          'on-accent': '#0b1226',
        },
        accent: {
          DEFAULT: '#f5bc7a',
          hover: '#f8cfa0',
          soft: 'rgba(245, 188, 122, 0.22)',
          glow: 'rgba(245, 188, 122, 0.55)',
          dim: 'rgba(245, 188, 122, 0.10)',
          muted: 'rgba(244, 234, 214, 0.10)',
          secondary: 'rgba(244, 234, 214, 0.62)',
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
        success: '#8dd0a7',
        warning: '#f5bc7a',
        error: '#e88a8a',
        info: '#b9a3ff',
        border: {
          subtle: 'rgba(244, 234, 214, 0.10)',
          DEFAULT: 'rgba(244, 234, 214, 0.10)',
          strong: 'rgba(245, 188, 122, 0.30)',
          focus: '#f5bc7a',
          divider: 'rgba(244, 234, 214, 0.06)',
        },
        bubble: {
          userBg: 'rgba(245, 188, 122, 0.10)',
          userBorder: 'rgba(245, 188, 122, 0.32)',
          miraBg: 'rgba(20, 30, 55, 0.85)',
          miraBorder: 'rgba(244, 234, 214, 0.08)',
        },
        status: {
          online: '#8dd0a7',
          reconnecting: '#f5bc7a',
          offline: '#e88a8a',
        },
      },
      fontFamily: {
        serif: ['"Cormorant Garamond"', 'Georgia', 'serif'],
        sans: ['Manrope', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      borderRadius: {
        bubble: '16px',
        card: '12px',
        pill: '999px',
        button: '10px',
        input: '18px',
        'input-mobile': '22px',
        'sidebar-item': '8px',
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
