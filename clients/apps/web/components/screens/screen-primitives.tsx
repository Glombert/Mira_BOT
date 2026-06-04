'use client';

import React from 'react';
import { Spark } from '../chat/aurora-cards';

/* ── Section header with label + title + subtitle + actions ── */
export function SectionHeader({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div
      className="flex items-end gap-5 relative z-[2]"
      style={{
        padding: '24px 32px 18px',
        borderBottom: '1px solid rgba(244,234,214,0.06)',
      }}
    >
      <div className="flex-1">
        <div
          className="uppercase text-[10px] font-semibold tracking-[0.18em] mb-2"
          style={{ color: '#f5bc7a' }}
        >
          раздел
        </div>
        <div
          className="font-serif italic"
          style={{
            fontSize: 34,
            color: '#f4ead6',
            lineHeight: 1.05,
            letterSpacing: '0.01em',
          }}
        >
          {title}
        </div>
        {subtitle && (
          <div
            className="font-serif italic mt-1.5"
            style={{
              fontSize: 13,
              color: 'rgba(244,234,214,0.62)',
            }}
          >
            {subtitle}
          </div>
        )}
      </div>
      {actions && <div className="flex gap-2">{actions}</div>}
    </div>
  );
}

/* ── Primary button ────────────────────────────────────────── */
export function PrimaryBtn({
  children,
  gold = false,
  onClick,
}: {
  children: React.ReactNode;
  gold?: boolean;
  onClick?: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="inline-flex items-center gap-2 h-9 px-4 text-xs font-medium tracking-wide rounded-lg transition-colors"
      style={{
        background: gold ? '#f5bc7a' : 'rgba(255,255,255,0.03)',
        border: gold ? 'none' : '1px solid rgba(244,234,214,0.10)',
        color: gold ? '#070c1c' : '#f4ead6',
      }}
    >
      {children}
    </button>
  );
}

/* ── Form row (label + value + action) ─────────────────────── */
export function FormRow({
  label,
  value,
  hint,
  monoValue,
  action,
}: {
  label: string;
  value: React.ReactNode;
  hint?: string;
  monoValue?: boolean;
  action?: React.ReactNode;
}) {
  return (
    <div
      className="flex items-start gap-6"
      style={{ padding: '14px 0', borderBottom: '1px solid rgba(244,234,214,0.06)' }}
    >
      <div className="w-44 shrink-0 pt-0.5">
        <div className="uppercase text-[10px] font-semibold tracking-[0.18em] text-text-muted mb-1">
          {label}
        </div>
        {hint && (
          <div className="text-[11px] leading-relaxed font-serif italic" style={{ color: 'rgba(244,234,214,0.22)' }}>
            {hint}
          </div>
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div
          className="leading-snug"
          style={{
            fontSize: monoValue ? 13 : 14.5,
            color: '#f4ead6',
            fontFamily: monoValue ? '"JetBrains Mono", monospace' : 'Manrope, sans-serif',
          }}
        >
          {value}
        </div>
      </div>
      {action && <div className="pt-0.5">{action}</div>}
    </div>
  );
}

/* ── Chip toggle ───────────────────────────────────────────── */
export function ChipToggle({
  children,
  active = false,
  onClick,
}: {
  children: React.ReactNode;
  active?: boolean;
  onClick?: () => void;
}) {
  return (
    <span
      onClick={onClick}
      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-pill text-xs mr-1.5 cursor-pointer transition-colors"
      style={{
        background: active ? 'rgba(245,188,122,0.10)' : 'transparent',
        border: `1px solid ${active ? 'rgba(245,188,122,0.30)' : 'rgba(244,234,214,0.10)'}`,
        color: active ? '#f5bc7a' : 'rgba(244,234,214,0.62)',
      }}
    >
      {children}
    </span>
  );
}

/* ── Preference row ────────────────────────────────────────── */
export function PrefRow({
  icon,
  label,
  value,
  mono,
  status,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  mono?: boolean;
  status?: 'ok';
}) {
  return (
    <div
      className="flex items-center gap-3.5"
      style={{ padding: '10px 0', borderBottom: '1px solid rgba(244,234,214,0.06)' }}
    >
      <div
        className="w-7 h-7 rounded-md shrink-0 flex items-center justify-center"
        style={{
          background: 'rgba(245,188,122,0.06)',
          border: '1px solid rgba(244,234,214,0.10)',
          color: '#f5bc7a',
        }}
      >
        {icon}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-[12.5px]" style={{ color: '#f4ead6', marginBottom: 2 }}>{label}</div>
        <div
          className="text-[11px] text-text-muted"
          style={{
            fontFamily: mono ? '"JetBrains Mono", monospace' : 'inherit',
            letterSpacing: mono ? '0.02em' : 0,
          }}
        >
          {value}
        </div>
      </div>
      {status === 'ok' && (
        <div
          className="w-1.5 h-1.5 rounded-full"
          style={{ background: '#8dd0a7', boxShadow: '0 0 6px #8dd0a7' }}
        />
      )}
    </div>
  );
}

/* ── Edit pen icon ─────────────────────────────────────────── */
export function EditPen() {
  return (
    <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
      <path
        d="M2 13 L4 12.5 L12 4.5 L11.5 4 L3.5 12 Z M10 5.5 L11 6.5"
        stroke="currentColor"
        strokeWidth="1.1"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/* ── Screen shell (sidebar replacement layout) ─────────────── */
export function ScreenShell({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div
      className="flex-1 flex flex-col relative z-[1] overflow-hidden"
    >
      {children}
    </div>
  );
}
