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
          base: '#0d0c0f',
          elevated: '#16151a',
          overlay: '#1e1d23',
          input: '#15141a',
        },
        text: {
          primary: '#eae6dc',
          secondary: '#a8a39c',
          muted: '#6e6a64',
          'on-accent': '#1a1410',
        },
        accent: {
          DEFAULT: '#FF8C42',
          hover: '#FFA060',
          soft: '#FFB888',
          glow: 'rgba(255, 140, 66, 0.15)',
        },
        success: '#7BB661',
        warning: '#E8A24A',
        error: '#D9534F',
        info: '#7B9FD4',
        border: {
          subtle: 'rgba(234, 230, 220, 0.06)',
          DEFAULT: 'rgba(234, 230, 220, 0.12)',
          focus: '#FF8C42',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      borderRadius: {
        card: '16px',
        button: '8px',
        input: '8px',
      },
      boxShadow: {
        soft: '0 2px 8px rgba(0, 0, 0, 0.3), 0 0 1px rgba(255, 140, 66, 0.06)',
        elevated: '0 8px 24px rgba(0, 0, 0, 0.4), 0 0 2px rgba(255, 140, 66, 0.08)',
        glow: '0 0 24px rgba(255, 140, 66, 0.18)',
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
      },
    },
  },
  plugins: [],
};

export default config;
