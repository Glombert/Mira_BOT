'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { SectionHeader, PrimaryBtn, ScreenShell } from './screen-primitives';
import { Spark } from '../chat/aurora-cards';
import type { MiraClient } from '@mira/shared';

interface Reminder {
  id: string;
  title: string;
  at: string;
  gcal: boolean;
  repeat?: string | null;
  miraNote?: string;
  done: boolean;
}

interface ReminderBucket {
  bucket: string;
  label: string;
  items: Reminder[];
}

const RemIco = {
  check: (c = 'currentColor') => <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M3.5 8.5 L6.5 11.5 L12.5 5" stroke={c} strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/></svg>,
  snooze: (c = 'currentColor') => <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="9" r="5" stroke={c} strokeWidth="1.2"/><path d="M8 6.5 V9 L9.8 10.2 M5.5 3 L3.3 5 M10.5 3 L12.7 5" stroke={c} strokeWidth="1.2" strokeLinecap="round"/></svg>,
  repeat: (c = 'currentColor') => <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M3 7 A4 4 0 0 1 11 6 M11 3 V6 H8 M13 9 A4 4 0 0 1 5 10 M5 13 V10 H8" stroke={c} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>,
};

function GCalBadge() {
  return (
    <div
      className="inline-flex items-center gap-1.5 h-5 px-1.5 rounded-pill text-[9.5px] tracking-wide"
      title="синхронизировано с Google Calendar"
      style={{ background: 'rgba(141,208,167,0.10)', border: '1px solid rgba(141,208,167,0.30)', color: '#8dd0a7' }}
    >
      <svg width="11" height="11" viewBox="0 0 16 16" fill="none"><rect x="2.5" y="3.5" width="11" height="10" rx="1" stroke="currentColor" strokeWidth="1.1"/><path d="M5 2 V5 M11 2 V5 M2.5 6.5 H13.5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round"/></svg>
      Calendar
    </div>
  );
}

function ReminderRow({ r }: { r: Reminder }) {
  return (
    <div className="flex gap-3.5 items-start py-3.5 relative" style={{ opacity: r.done ? 0.5 : 1 }}>
      <div className="w-[72px] shrink-0 text-right pt-0.5">
        <div className="text-sm font-mono font-medium tracking-tight" style={{ color: '#f4ead6' }}>{r.at}</div>
      </div>
      <div className="shrink-0 flex flex-col items-center pt-1">
        <div
          className="w-[11px] h-[11px] rounded-full flex items-center justify-center"
          style={{
            background: r.done ? 'transparent' : 'rgba(244,234,214,0.15)',
            border: r.done ? '1.5px solid #8dd0a7' : '1.5px solid rgba(244,234,214,0.36)',
          }}
        >
          {r.done && RemIco.check('#8dd0a7')}
        </div>
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium" style={{ color: '#f4ead6', textDecoration: r.done ? 'line-through' : 'none', textDecorationColor: 'rgba(244,234,214,0.36)' }}>{r.title}</span>
          {r.gcal && <GCalBadge />}
          {r.repeat && (
            <span className="inline-flex items-center gap-1 text-[10.5px] tracking-wide" style={{ color: '#b9a3ff' }}>
              {RemIco.repeat('#b9a3ff')} {r.repeat}
            </span>
          )}
        </div>
        {r.miraNote && (
          <div className="flex gap-1.5 items-start mt-1">
            <span className="text-gold shrink-0 mt-0.5"><Spark size={9} color="#f5bc7a" /></span>
            <span className="font-serif italic text-xs leading-snug" style={{ color: 'rgba(244,234,214,0.62)' }}>{r.miraNote}</span>
          </div>
        )}
      </div>
      {!r.done && (
        <div className="flex gap-1.5 shrink-0 pt-0.5">
          <button className="w-[30px] h-[30px] rounded-md inline-flex items-center justify-center" style={{ border: '1px solid rgba(244,234,214,0.10)', color: 'rgba(244,234,214,0.62)' }}>{RemIco.snooze()}</button>
          <button className="w-[30px] h-[30px] rounded-md inline-flex items-center justify-center" style={{ border: '1px solid rgba(141,208,167,0.30)', color: '#8dd0a7' }}>{RemIco.check('#8dd0a7')}</button>
        </div>
      )}
    </div>
  );
}

function MonthView() {
  const weekdays = ['пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс'];
  const daysInMonth = 30;
  const firstWeekday = 0;
  const cells: (number | null)[] = [];
  for (let i = 0; i < firstWeekday; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);
  while (cells.length % 7 !== 0) cells.push(null);
  const [sel, setSel] = useState(4);

  return (
    <div className="flex gap-0">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-3 mb-3.5">
          <div className="font-serif italic text-[22px]" style={{ color: '#f4ead6' }}>Июнь <span className="text-text-muted">2026</span></div>
          <div className="flex-1" />
        </div>
        <div className="grid grid-cols-7 gap-2 mb-2">
          {weekdays.map((w, i) => (
            <div key={i} className="text-center text-[10px] text-text-muted tracking-widest lowercase font-mono">{w}</div>
          ))}
        </div>
        <div className="grid grid-cols-7 gap-2">
          {cells.map((d, i) => {
            if (d === null) return <div key={i} />;
            const isToday = d === 4;
            const isSel = d === sel;
            return (
              <button
                key={i}
                onClick={() => setSel(d)}
                className="aspect-square rounded-lg p-1.5 flex flex-col items-center justify-start gap-1 relative cursor-pointer transition-colors"
                style={{
                  background: isSel ? 'rgba(245,188,122,0.10)' : isToday ? 'rgba(245,188,122,0.04)' : 'transparent',
                  border: isSel ? '1px solid rgba(245,188,122,0.30)' : isToday ? '1px solid rgba(244,234,214,0.10)' : '1px solid transparent',
                }}
              >
                <span className={`text-[13px] font-mono ${isToday ? 'text-gold font-bold' : 'text-text-primary'}`}>{d}</span>
              </button>
            );
          })}
        </div>
        <div className="flex gap-4 mt-3.5 pt-3" style={{ borderTop: '1px solid rgba(244,234,214,0.06)' }}>
          <span className="inline-flex items-center gap-1.5 text-[10.5px] text-text-muted">
            <span className="w-1.5 h-1.5 rounded-full bg-sage" /> Google Calendar
          </span>
          <span className="inline-flex items-center gap-1.5 text-[10.5px] text-text-muted">
            <span className="w-1.5 h-1.5 rounded-full bg-gold" /> личное напоминание
          </span>
        </div>
      </div>
      <div className="w-[300px] shrink-0 pl-6" style={{ borderLeft: '1px solid rgba(244,234,214,0.06)' }}>
        <div className="uppercase text-[10px] font-semibold tracking-[0.18em] text-gold mb-3">
          {sel === 4 ? 'сегодня · 4 июня' : `${sel} июня`}
        </div>
        <div className="font-serif italic text-sm text-text-dim">в этот день — свободно. хочешь, спланируем что-нибудь?</div>
      </div>
    </div>
  );
}

function ViewToggle({ view, setView }: { view: 'list' | 'month'; setView: (v: 'list' | 'month') => void }) {
  return (
    <div className="flex gap-0.5 p-1 rounded-lg" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(244,234,214,0.10)' }}>
      {(['list', 'month'] as const).map((id) => (
        <button
          key={id}
          onClick={() => setView(id)}
          className="h-7 px-3 rounded-md text-xs tracking-wide transition-colors"
          style={{
            background: view === id ? 'rgba(245,188,122,0.10)' : 'transparent',
            border: view === id ? '1px solid rgba(245,188,122,0.30)' : '1px solid transparent',
            color: view === id ? '#f5bc7a' : 'rgba(244,234,214,0.62)',
          }}
        >
          {id === 'list' ? 'Список' : 'Месяц'}
        </button>
      ))}
    </div>
  );
}

interface RemindersScreenProps {
  client: MiraClient | null;
}

export function RemindersScreen({ client }: RemindersScreenProps) {
  const [view, setView] = useState<'list' | 'month'>('list');
  const [buckets, setBuckets] = useState<ReminderBucket[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!client) return;
    setLoading(true);
    try {
      const msg = await client.sendCommandAwait('reminders', ['system', 'message'], 8000);
      // TODO: parse structured reminders when backend supports it
      setBuckets([]);
    } catch {
      setBuckets([]);
    } finally {
      setLoading(false);
    }
  }, [client]);

  useEffect(() => {
    load();
  }, [load]);

  const total = buckets.reduce((n, b) => n + b.items.length, 0);
  const gcalCount = buckets.reduce((n, b) => n + b.items.filter((i) => i.gcal).length, 0);

  return (
    <ScreenShell>
      <SectionHeader
        title="Напоминания"
        subtitle="Мира помнит за тебя · важное уходит в Google Calendar"
        actions={
          <>
            <ViewToggle view={view} setView={setView} />
            <PrimaryBtn gold>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="inline mr-1"><path d="M7 2 V12 M2 7 H12" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>
              новое
            </PrimaryBtn>
          </>
        }
      />

      {/* gcal sync strip */}
      <div
        className="flex items-center gap-3.5 relative z-[2]"
        style={{ padding: '14px 32px', borderBottom: '1px solid rgba(244,234,214,0.06)' }}
      >
        <div
          className="w-[34px] h-[34px] rounded-lg shrink-0 flex items-center justify-center"
          style={{ background: 'rgba(141,208,167,0.10)', border: '1px solid rgba(141,208,167,0.30)', color: '#8dd0a7' }}
        >
          <svg width="18" height="18" viewBox="0 0 16 16" fill="none"><rect x="2.5" y="3.5" width="11" height="10" rx="1" stroke="currentColor" strokeWidth="1.1"/><path d="M5 2 V5 M11 2 V5 M2.5 6.5 H13.5" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round"/></svg>
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[12.5px] font-medium" style={{ color: '#f4ead6' }}>Google Calendar подключён</div>
          <div className="text-[11px] text-text-muted mt-0.5 font-mono">
            {gcalCount} из {total} напоминаний синхронизированы
          </div>
        </div>
        <div
          className="w-[40px] h-[22px] rounded-pill p-0.5 flex items-center justify-end"
          style={{ background: 'rgba(245,188,122,0.10)', border: '1px solid rgba(245,188,122,0.30)' }}
        >
          <div className="w-4 h-4 rounded-full bg-gold" />
        </div>
      </div>

      {/* body */}
      <div className="flex-1 overflow-y-auto mira-scroll" style={{ padding: '16px 32px 40px' }}>
        {loading ? (
          <div className="text-center text-text-muted text-sm py-10">Загрузка напоминаний…</div>
        ) : view === 'month' ? (
          <MonthView />
        ) : buckets.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-text-muted">
            <svg width="48" height="48" viewBox="0 0 28 28" fill="none">
              <defs>
                <linearGradient id="emptyRem" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#f5bc7a" stopOpacity="0.3" />
                  <stop offset="1" stopColor="#f8cfa0" stopOpacity="0.2" />
                </linearGradient>
              </defs>
              <path d="M4 11 V8 A4 4 0 0 1 12 8 V11 L13 12 H3 Z M7 13.5 A1 1 0 0 0 9 13.5" fill="url(#emptyRem)" />
            </svg>
            <p className="text-sm text-text-secondary font-serif italic">Нет напоминаний</p>
          </div>
        ) : (
          <>
            {buckets.map((bucket, bi) => (
              <div key={bi} className="mb-7">
                <div className="flex items-center gap-3 mb-1.5">
                  <span className="uppercase text-[10px] font-semibold tracking-[0.18em] text-gold">{bucket.label}</span>
                  <div className="flex-1 h-px" style={{ background: 'linear-gradient(90deg, rgba(244,234,214,0.06), transparent)' }} />
                </div>
                <div className="relative">
                  <div className="absolute left-[91px] top-4 bottom-4 w-px" style={{ background: 'rgba(244,234,214,0.06)' }} />
                  {bucket.items.map((r, ri) => (
                    <ReminderRow key={ri} r={r} />
                  ))}
                </div>
              </div>
            ))}
            <div
              className="flex items-center gap-3 mt-2 px-4 py-4 rounded-[10px]"
              style={{ border: '1px dashed rgba(244,234,214,0.10)' }}
            >
              <span className="text-text-muted"><Spark size={12} color="#b9a3ff" /></span>
              <span className="font-serif italic text-[13.5px] leading-snug" style={{ color: 'rgba(244,234,214,0.62)' }}>
                «Скажи мне просто словами — "напомни завтра в 9 позвонить Кате" — и я добавлю сама.»
              </span>
            </div>
          </>
        )}
      </div>
    </ScreenShell>
  );
}
