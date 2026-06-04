'use client';

import React from 'react';

interface AuroraWelcomeProps {
  userName?: string;
  compact?: boolean;
}

export function AuroraWelcome({ userName, compact = false }: AuroraWelcomeProps) {
  const portraitSize = compact ? 96 : 140;
  return (
    <div
      className="text-center relative"
      style={{ padding: compact ? '24px 20px 12px' : '36px 28px 12px' }}
    >
      <div
        className="relative mx-auto"
        style={{
          width: portraitSize,
          height: portraitSize,
          marginBottom: compact ? 14 : 18,
        }}
      >
        {/* orbit ring */}
        <div
          className="mira-orbit-slow absolute rounded-full"
          style={{
            inset: -12,
            border: '1px dashed rgba(245,188,122,0.30)',
            opacity: 0.7,
          }}
        />
        {/* breathing glow */}
        <div
          className="mira-breathe absolute rounded-full"
          style={{
            inset: -28,
            background: 'radial-gradient(circle, rgba(245,188,122,0.55) 0%, transparent 65%)',
          }}
        />
        {/* portrait */}
        <div
          className="absolute inset-0 rounded-full overflow-hidden"
          style={{
            border: '1px solid rgba(245,188,122,0.30)',
            background: '#1a1f2e',
          }}
        >
          <img
            src="/mira-avatar-full.png"
            alt="Мира"
            className="w-full h-full block object-cover"
            style={{ objectPosition: '50% 22%' }}
          />
        </div>
      </div>

      <div
        className="font-serif italic"
        style={{
          fontSize: compact ? 24 : 32,
          color: '#f4ead6',
          fontWeight: 400,
          letterSpacing: '0.01em',
          marginBottom: 4,
        }}
      >
        Добро пожаловать{userName ? ',' : ''}{' '}
        <span style={{ color: '#f5bc7a' }}>{userName || 'друг'}</span>
      </div>
      <div
        className="font-serif italic"
        style={{
          fontSize: compact ? 15 : 18,
          color: 'rgba(244,234,214,0.62)',
          marginBottom: compact ? 14 : 18,
          maxWidth: 500,
          margin: `0 auto ${compact ? 14 : 18}px`,
          lineHeight: 1.4,
        }}
      >
        Расскажи, что у тебя на душе — или просто помолчи рядом.
      </div>

      <div
        className="flex gap-2 justify-center flex-wrap"
        style={{ marginBottom: compact ? 18 : 28 }}
      >
        {['Чем заняться сегодня?', 'Напомни мне позже', 'Расскажи что-нибудь'].map((c, i) => (
          <button
            key={i}
            className="px-3.5 py-1.5 rounded-pill text-[12.5px] transition-colors hover:bg-white/[0.04]"
            style={{
              border: '1px solid rgba(244,234,214,0.10)',
              background: 'rgba(255,255,255,0.02)',
              color: 'rgba(244,234,214,0.62)',
            }}
          >
            {c}
          </button>
        ))}
      </div>

      <div
        className="h-px mx-auto"
        style={{
          width: 80,
          background: 'linear-gradient(90deg, transparent, rgba(245,188,122,0.30), transparent)',
        }}
      />
    </div>
  );
}
