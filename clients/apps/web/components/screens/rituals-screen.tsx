'use client';

import React, { useState, useEffect, useCallback } from 'react';
import type { MiraClient } from '@mira/shared';
import { SectionHeader, PrimaryBtn, ScreenShell } from './screen-primitives';
import { Spark } from '../chat/aurora-cards';

interface Ritual {
  mark: string;
  name: string;
  time: string;
  days: boolean[];
  desc: string;
  last: string;
  next: string;
  on: boolean;
  color: string;
}

const _MONTHS = ['янв','фев','мар','апр','мая','июн','июл','авг','сен','окт','ноя','дек'];

function _markFor(name: string): string {
  const n = (name || '').toLowerCase();
  if (n.includes('review') || n.includes('evolve') || n.includes('version')) return 'evolve';
  if (n.includes('backup') || n.includes('health') || n.includes('server')) return 'backup';
  if (n.includes('summary') || n.includes('weekly') || n.includes('digest')) return 'diary';
  if (n.includes('audit') || n.includes('log')) return 'review';
  return 'personality';
}

function _colorFor(name: string): string {
  const m = _markFor(name);
  return m === 'evolve' ? '#b9a3ff' : m === 'backup' ? '#8dd0a7' : '#f5bc7a';
}

function _humanSchedule(cron: string): string {
  const p = (cron || '').trim().split(/\s+/);
  if (p.length < 5) return cron || '—';
  const [min, hr, dom, , dow] = p;
  const time = `${hr.padStart(2, '0')}:${min.padStart(2, '0')}`;
  if (dom !== '*') return `${dom} числа · ${time}`;
  if (dow !== '*') return `дни ${dow} · ${time}`;
  return `ежедневно · ${time}`;
}

function _fmtRun(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '—';
  return `${d.getDate()} ${_MONTHS[d.getMonth()]} · ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function _mapRitual(r: any): Ritual {
  return {
    mark: _markFor(r.name),
    name: r.name || '',
    time: _humanSchedule(r.schedule || ''),
    days: Array.isArray(r.days) && r.days.length === 7 ? r.days : [false, false, false, false, false, false, false],
    desc: r.description || '',
    last: _fmtRun(r.last_run),
    next: _fmtRun(r.next_run),
    on: r.enabled !== false,
    color: _colorFor(r.name),
  };
}

const DAY_LABELS = ['П', 'В', 'С', 'Ч', 'П', 'С', 'В'];

function WeekStrip({ days }: { days: boolean[] }) {
  return (
    <div className="flex gap-1">
      {DAY_LABELS.map((l, i) => (
        <div
          key={i}
          className="w-5 h-5 rounded flex items-center justify-center text-[9.5px] font-mono"
          style={{
            background: days[i] ? 'rgba(245,188,122,0.10)' : 'transparent',
            border: `1px solid ${days[i] ? 'rgba(245,188,122,0.30)' : 'rgba(244,234,214,0.10)'}`,
            color: days[i] ? '#f5bc7a' : 'rgba(244,234,214,0.22)',
            fontWeight: days[i] ? 600 : 400,
          }}
        >{l}</div>
      ))}
    </div>
  );
}

function Toggle({ on }: { on: boolean }) {
  return (
    <div
      className="w-[38px] h-[21px] rounded-pill p-0.5 flex items-center shrink-0"
      style={{
        background: on ? 'rgba(245,188,122,0.10)' : 'rgba(255,255,255,0.04)',
        border: `1px solid ${on ? 'rgba(245,188,122,0.30)' : 'rgba(244,234,214,0.10)'}`,
        justifyContent: on ? 'flex-end' : 'flex-start',
      }}
    >
      <div className="w-[15px] h-[15px] rounded-full" style={{ background: on ? '#f5bc7a' : 'rgba(244,234,214,0.36)' }} />
    </div>
  );
}

function RitualIcon({ mark }: { mark: string }) {
  return (
    <svg width="17" height="17" viewBox="0 0 16 16" fill="none">
      {mark === 'review' && (
        <path d="M7 7 A4 4 0 0 1 12 11.5 V13.5 M10 10 L13.5 13.5 M5.5 7 L6.5 8 L8.5 6" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round" />
      )}
      {mark === 'evolve' && (
        <g>
          <path d="M5 2.5 Q 8 5.5 5 8 Q 2 10.5 5 13.5 M11 2.5 Q 8 5.5 11 8 Q 14 10.5 11 13.5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" fill="none" />
          <circle cx="5" cy="5" r="0.6" fill="currentColor" />
          <circle cx="11" cy="11" r="0.6" fill="currentColor" />
          <circle cx="8" cy="8" r="0.6" fill="currentColor" />
        </g>
      )}
      {mark === 'backup' && (
        <path d="M2.5 5 L8 2.5 L13.5 5 V11 L8 13.5 L2.5 11 Z M2.5 5 L8 7.5 L13.5 5 M8 7.5 V13.5" stroke="currentColor" strokeWidth="1.1" strokeLinejoin="round" />
      )}
      {mark === 'diary' && (
        <g>
          <path d="M3 3 H12 A1 1 0 0 1 13 4 V13 A1 1 0 0 1 12 14 H3 Z" stroke="currentColor" strokeWidth="1.1" />
          <path d="M3 3 V14" stroke="currentColor" strokeWidth="1.1" />
          <path d="M5.5 6 H10.5 M5.5 8.5 H10.5 M5.5 11 H9" stroke="currentColor" strokeWidth="0.9" strokeOpacity="0.6" />
        </g>
      )}
      {mark === 'personality' && (
        <g>
          <path d="M3 13 V11 A3 3 0 0 1 6 8 H10 A3 3 0 0 1 13 11 V13" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
          <circle cx="8" cy="5" r="2.5" stroke="currentColor" strokeWidth="1.1" />
        </g>
      )}
    </svg>
  );
}

function RitualCard({ r }: { r: Ritual }) {
  return (
    <div
      className="flex flex-col gap-3 p-4 rounded-xl"
      style={{
        background: 'rgba(255,255,255,0.02)',
        border: '1px solid rgba(244,234,214,0.10)',
        opacity: r.on ? 1 : 0.6,
      }}
    >
      <div className="flex items-start gap-3">
        <div
          className="w-[34px] h-[34px] rounded-lg shrink-0 flex items-center justify-center"
          style={{ background: `${r.color}14`, border: `1px solid ${r.color}40`, color: r.color }}
        >
          <RitualIcon mark={r.mark} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold leading-tight" style={{ color: '#f4ead6' }}>{r.name}</div>
          <div className="inline-flex items-center gap-1 mt-1 text-[11px] font-mono" style={{ color: r.color }}>
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8.5" r="5" stroke="currentColor" strokeWidth="1.1"/><path d="M8 6 V8.5 L10 9.5 M5.5 3 L3.5 5 M10.5 3 L12.5 5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round"/></svg>
            {r.time}
          </div>
        </div>
        <Toggle on={r.on} />
      </div>
      <div className="font-serif italic text-[13.5px] leading-snug" style={{ color: 'rgba(244,234,214,0.62)' }}>{r.desc}</div>
      <div className="flex items-center gap-3 flex-wrap pt-3" style={{ borderTop: '1px solid rgba(244,234,214,0.06)' }}>
        <WeekStrip days={r.days} />
        <div className="flex-1" />
        <div className="text-[10.5px] text-text-muted font-mono text-right">
          <div>последний · {r.last}</div>
          <div className="text-gold/80">следующий · {r.next}</div>
        </div>
      </div>
    </div>
  );
}

export function RitualsScreen({ client }: { client: MiraClient | null }) {
  const [rituals, setRituals] = useState<Ritual[]>([]);

  const load = useCallback(async () => {
    if (!client) return;
    try {
      const msg = await client.sendCommandAwait('rituals_data', ['rituals_data'], 8000);
      if ('rituals' in msg && Array.isArray((msg as any).rituals)) {
        setRituals((msg as any).rituals.map(_mapRitual));
      }
    } catch {
      // оставляем пусто
    }
  }, [client]);

  useEffect(() => { load(); }, [load]);

  const active = rituals.filter((r) => r.on).length;
  return (
    <ScreenShell>
      <SectionHeader
        title="Ритуалы"
        subtitle="что Мира делает сама · по расписанию, в разные дни и часы"
        actions={
          <PrimaryBtn gold>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="inline mr-1"><path d="M7 2 V12 M2 7 H12" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>
            новый ритуал
          </PrimaryBtn>
        }
      />

      <div
        className="flex items-center gap-4 relative z-[2]"
        style={{ padding: '14px 32px', borderBottom: '1px solid rgba(244,234,214,0.06)' }}
      >
        <span className="text-[11.5px] text-text-muted font-mono">
          <span className="text-text-primary">{rituals.length}</span> ритуалов
        </span>
        <span className="text-[11.5px] text-text-muted font-mono">
          <span style={{ color: '#8dd0a7' }}>{active}</span> активны
        </span>
        <span className="text-[11.5px] text-text-muted font-mono">
          <span className="text-text-faint">{rituals.length - active}</span> на паузе
        </span>
      </div>

      <div className="flex-1 overflow-y-auto mira-scroll" style={{ padding: '24px 32px 40px' }}>
        <div className="grid grid-cols-2 gap-3.5">
          {rituals.map((r, i) => <RitualCard key={i} r={r} />)}
        </div>
        <div
          className="flex items-center gap-3 mt-5 px-4 py-4 rounded-[10px]"
          style={{ border: '1px dashed rgba(244,234,214,0.10)' }}
        >
          <span className="text-text-muted"><Spark size={12} color="#b9a3ff" /></span>
          <span className="font-serif italic text-[13.5px] leading-snug" style={{ color: 'rgba(244,234,214,0.62)' }}>
            «Ритуалы — это привычки, которые я держу за тебя. Хочешь, чтобы я что-то делала регулярно — просто скажи когда.»
          </span>
        </div>
      </div>
    </ScreenShell>
  );
}
