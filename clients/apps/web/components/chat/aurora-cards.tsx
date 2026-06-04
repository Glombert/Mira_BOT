'use client';

import React from 'react';

/* ── small sparkle ─────────────────────────────────────────── */
export function Spark({ size = 12, color = 'currentColor', style = {} }: { size?: number; color?: string; style?: React.CSSProperties }) {
  return (
    <svg width={size} height={size} viewBox="0 0 12 12" style={style}>
      <path d="M6 0 L7 5 L12 6 L7 7 L6 12 L5 7 L0 6 L5 5 Z" fill={color} />
    </svg>
  );
}

/* ── the "she's typing" indicator — 3 dots ─────────────────── */
export function TypingDots({ color = 'currentColor', size = 4 }: { color?: string; size?: number }) {
  return (
    <span style={{ display: 'inline-flex', gap: size, alignItems: 'center' }}>
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="mira-typing-dot"
          style={{ width: size, height: size, borderRadius: '50%', background: color }}
        />
      ))}
    </span>
  );
}

/* ── concentric ripples (Mira's "thinking" ring) ──────────── */
export function ThinkingRing({ size = 18, color = 'rgba(245,188,122,0.7)' }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 18 18" style={{ overflow: 'visible' }}>
      <circle cx="9" cy="9" r="3" fill={color} />
      <circle cx="9" cy="9" r="6" fill="none" stroke={color} strokeOpacity="0.5" strokeWidth="0.8" className="mira-twinkle" />
      <circle cx="9" cy="9" r="8.5" fill="none" stroke={color} strokeOpacity="0.25" strokeWidth="0.6" className="mira-twinkle" style={{ animationDelay: '0.7s' }} />
    </svg>
  );
}

/* ── Memory card ───────────────────────────────────────────── */
export interface AuroraMemoryProps {
  label: string;
  fact: string;
  list?: string[];
}

export function AuroraMemory({ label, fact, list }: AuroraMemoryProps) {
  return (
    <div
      className="mt-3 px-4 py-3 rounded-card"
      style={{
        background: 'rgba(245,188,122,0.06)',
        border: '1px dashed rgba(245,188,122,0.30)',
      }}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <Spark size={11} color="#f5bc7a" />
        <span
          className="uppercase text-[10px] font-semibold tracking-[0.18em]"
          style={{ color: '#f5bc7a' }}
        >
          {label}
        </span>
        <div className="flex-1 h-px" style={{ background: 'linear-gradient(90deg, rgba(245,188,122,0.30), transparent)' }} />
      </div>
      <div className="font-serif italic text-sm leading-snug" style={{ color: '#f4ead6', marginBottom: list ? 10 : 4 }}>
        {fact}
      </div>
      {list && list.length > 0 && (
        <div className="flex flex-col gap-1.5">
          {list.map((item, i) => (
            <div key={i} className="flex items-center gap-2.5 text-[13px] leading-relaxed" style={{ color: '#f4ead6' }}>
              <span
                className="shrink-0 w-3.5 h-3.5 rounded-sm inline-flex items-center justify-center"
                style={{ border: '1px solid rgba(245,188,122,0.30)' }}
              >
                <span className="w-1 h-1 rounded-full bg-gold" />
              </span>
              {item}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ── Thinking process ──────────────────────────────────────── */
export interface AuroraThinkingProps {
  label: string;
  steps: string[];
}

export function AuroraThinking({ label, steps }: AuroraThinkingProps) {
  return (
    <div className="flex gap-3 items-start max-w-[82%] mira-rise">
      <div className="w-9 pt-1.5 shrink-0">
        <ThinkingRing size={20} color="#f5bc7a" />
      </div>
      <div
        className="flex-1 px-5 py-3.5 rounded-[14px] relative overflow-hidden"
        style={{
          background: 'linear-gradient(135deg, rgba(245,188,122,0.04), rgba(185,163,255,0.04))',
          border: '1px solid rgba(244,234,214,0.10)',
        }}
      >
        <div className="mira-shimmer absolute inset-0 pointer-events-none opacity-40" />
        <div className="flex items-center gap-2 mb-3 relative">
          <span className="uppercase text-[10px] font-semibold tracking-[0.18em] text-gold">{label}</span>
          <TypingDots color="#f5bc7a" />
        </div>
        <div className="flex flex-col gap-[7px] relative">
          {steps.map((step, i) => (
            <div key={i} className="flex items-start gap-2.5 font-mono text-[11.5px] leading-relaxed" style={{ color: 'rgba(244,234,214,0.62)' }}>
              <span className="text-gold/70 mt-0.5 shrink-0">{String(i + 1).padStart(2, '0')}</span>
              <span className="w-[18px] h-px mt-2 shrink-0" style={{ background: 'rgba(245,188,122,0.30)' }} />
              <span>{step}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ── Event card (Calendar) ─────────────────────────────────── */
export interface AuroraEventCardProps {
  label: string;
  title: string;
  time: string;
  sub?: string;
  date?: { month: string; day: string };
}

export function AuroraEventCard({ label, title, time, sub, date }: AuroraEventCardProps) {
  return (
    <div
      className="mt-3 px-4 py-3.5 rounded-card flex gap-3.5 items-start"
      style={{
        background: 'rgba(141, 208, 167, 0.06)',
        border: '1px solid rgba(141, 208, 167, 0.30)',
      }}
    >
      <div
        className="w-10 h-11 rounded-md shrink-0 flex flex-col items-center justify-center"
        style={{
          background: 'rgba(141, 208, 167, 0.12)',
          border: '1px solid rgba(141, 208, 167, 0.35)',
          color: '#8dd0a7',
        }}
      >
        <div className="text-[9px] opacity-80 tracking-widest uppercase">{date?.month ?? '---'}</div>
        <div className="font-serif text-lg leading-none font-semibold">{date?.day ?? '--'}</div>
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="uppercase text-[10px] font-semibold tracking-[0.18em]" style={{ color: '#8dd0a7' }}>{label}</span>
        </div>
        <div className="font-serif text-base font-medium leading-tight" style={{ color: '#f4ead6' }}>{title}</div>
        <div className="text-xs mt-1 font-mono tracking-wide" style={{ color: '#f4ead6' }}>{time}</div>
        {sub && <div className="text-[11.5px] mt-1.5 leading-relaxed" style={{ color: 'rgba(244,234,214,0.36)' }}>{sub}</div>}
      </div>
    </div>
  );
}

/* ── Backup card ───────────────────────────────────────────── */
export interface AuroraBackupCardProps {
  label: string;
  title: string;
  size: string;
  sub?: string;
}

export function AuroraBackupCard({ label, title, size, sub }: AuroraBackupCardProps) {
  return (
    <div
      className="mt-2.5 px-4 py-3.5 rounded-card flex gap-3.5 items-start"
      style={{
        background: 'rgba(185, 163, 255, 0.06)',
        border: '1px solid rgba(185, 163, 255, 0.28)',
      }}
    >
      <div
        className="w-10 h-11 rounded-md shrink-0 flex items-center justify-center"
        style={{
          background: 'rgba(185, 163, 255, 0.10)',
          border: '1px solid rgba(185, 163, 255, 0.30)',
          color: '#b9a3ff',
        }}
      >
        <svg width="18" height="18" viewBox="0 0 16 16" fill="none">
          <path d="M2.5 5 L8 2.5 L13.5 5 V11 L8 13.5 L2.5 11 Z M2.5 5 L8 7.5 L13.5 5 M8 7.5 V13.5" stroke="currentColor" strokeWidth="1.1" strokeLinejoin="round" />
        </svg>
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 mb-1">
          <span className="uppercase text-[10px] font-semibold tracking-[0.18em]" style={{ color: '#b9a3ff' }}>{label}</span>
        </div>
        <div className="font-serif text-base font-medium leading-tight" style={{ color: '#f4ead6' }}>{title}</div>
        <div className="text-xs mt-1 font-mono tracking-wide" style={{ color: '#f4ead6' }}>{size}</div>
        {sub && <div className="text-[11.5px] mt-1.5 leading-relaxed" style={{ color: 'rgba(244,234,214,0.36)' }}>{sub}</div>}
      </div>
    </div>
  );
}

/* ── "I noticed" — Mira's self-learning surface ────────────── */
export interface AuroraLearnedProps {
  label?: string;
  text: string;
}

export function AuroraLearned({ label = 'я заметила', text }: AuroraLearnedProps) {
  return (
    <div className="flex justify-center my-1 mira-rise">
      <div
        className="max-w-[78%] px-5 py-3 rounded-pill flex items-center gap-3"
        style={{
          background: 'rgba(185,163,255,0.06)',
          border: '1px solid rgba(185,163,255,0.20)',
        }}
      >
        <span className="uppercase text-[10px] font-semibold tracking-[0.18em] shrink-0" style={{ color: '#b9a3ff' }}>
          ☾ {label}
        </span>
        <span className="font-serif italic text-sm leading-snug" style={{ color: '#f4ead6' }}>
          {text}
        </span>
      </div>
    </div>
  );
}

/* ── Reactions ─────────────────────────────────────────────── */
export function AuroraReactions({ items }: { items: string[] }) {
  return (
    <div className="flex gap-2 pl-12 -mt-1 flex-wrap">
      {items.map((it, i) => (
        <button
          key={i}
          className="px-2.5 py-1 rounded-pill text-[11px] tracking-wide"
          style={{
            border: '1px solid rgba(244,234,214,0.10)',
            background: 'rgba(255,255,255,0.02)',
            color: 'rgba(244,234,214,0.62)',
          }}
        >
          {it}
        </button>
      ))}
    </div>
  );
}
