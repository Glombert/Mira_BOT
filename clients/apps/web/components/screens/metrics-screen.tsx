'use client';

import React, { useState, useEffect, useCallback } from 'react';
import type { MiraClient } from '@mira/shared';
import { SectionHeader, ChipToggle, ScreenShell } from './screen-primitives';

type ModelRow = { name: string; req: string; tok: string; lat: string; cost: string; color: string; share: number };

const _MODEL_COLORS = ['#f5bc7a', '#8dd0a7', '#b9a3ff', '#7aa6f5', '#e88a8a'];

function _fmtTokens(t: number): string {
  if (t >= 1_000_000) return `${(t / 1_000_000).toFixed(2)}M`;
  if (t >= 1000) return `${(t / 1000).toFixed(0)}K`;
  return String(t);
}

function _mapModels(byModel: any[], totalCalls: number): ModelRow[] {
  return (byModel || []).map((m, i) => ({
    name: m.model,
    req: String(m.calls ?? 0),
    tok: _fmtTokens(m.tokens ?? 0),
    lat: '—',
    cost: `$${(m.cost ?? 0).toFixed(2)}`,
    color: _MODEL_COLORS[i % _MODEL_COLORS.length],
    share: totalCalls ? Math.round(((m.calls ?? 0) / totalCalls) * 100) : 0,
  }));
}

function AreaChart({ data, w = 560, h = 120, color = '#f5bc7a' }: { data: number[]; w?: number; h?: number; color?: string }) {
  const max = Math.max(...data) * 1.15;
  const stepX = w / (data.length - 1);
  const y = (v: number) => h - (v / max) * h;
  const pts = data.map((v, i) => `${i * stepX},${y(v)}`);
  const line = `M ${pts.join(' L ')}`;
  const area = `${line} L ${w},${h} L 0,${h} Z`;
  const gid = `grad-${color.replace(/[^a-z0-9]/gi, '')}`;
  return (
    <svg width="100%" height={h} viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" style={{ display: 'block', overflow: 'visible' }}>
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.28" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={area} fill={`url(#${gid})`} />
      <path d={line} fill="none" stroke={color} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={(data.length - 1) * stepX} cy={y(data[data.length - 1])} r="3.5" fill={color} />
    </svg>
  );
}

function Kpi({ label, value, unit, delta, deltaUp, sub }: { label: string; value: string; unit?: string; delta?: string; deltaUp?: boolean; sub?: string }) {
  return (
    <div className="flex-1 min-w-0 p-4 rounded-xl" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(244,234,214,0.10)' }}>
      <div className="uppercase text-[10px] font-semibold tracking-[0.18em] text-text-muted mb-2.5">{label}</div>
      <div className="flex items-baseline gap-1.5">
        <span className="text-[28px] font-mono tracking-tight leading-none" style={{ color: '#f4ead6' }}>{value}</span>
        {unit && <span className="text-[13px] text-text-muted">{unit}</span>}
        {delta && (
          <span className="ml-auto text-[11.5px] font-mono inline-flex items-center gap-1" style={{ color: deltaUp ? '#8dd0a7' : '#e88a8a' }}>
            {deltaUp ? '▲' : '▼'} {delta}
          </span>
        )}
      </div>
      {sub && <div className="text-[11px] text-text-muted mt-2 font-mono">{sub}</div>}
    </div>
  );
}

function DonutChart({ models, size = 100 }: { models: ModelRow[]; size?: number }) {
  const r = size / 2 - 8;
  const cx = size / 2, cy = size / 2;
  const circ = 2 * Math.PI * r;
  let offset = 0;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ flexShrink: 0, transform: 'rotate(-90deg)' }}>
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="10" />
      {models.map((m, i) => {
        const len = (m.share / 100) * circ;
        const el = (
          <circle key={i} cx={cx} cy={cy} r={r} fill="none"
            stroke={m.color} strokeWidth="10"
            strokeDasharray={`${len} ${circ - len}`}
            strokeDashoffset={-offset}
            strokeLinecap="butt" />
        );
        offset += len;
        return el;
      })}
    </svg>
  );
}

export function MetricsScreen({ client }: { client: MiraClient | null }) {
  const [models, setModels] = useState<ModelRow[]>([]);
  const [req14d, setReq14d] = useState<number[]>([]);
  const [totals, setTotals] = useState({ calls: 0, tokens: 0, cost: 0, days: 7 });

  const load = useCallback(async () => {
    if (!client) return;
    try {
      const msg: any = await client.sendCommandAwait('metrics_data', ['metrics_data'], 12000);
      if (msg && msg.type === 'metrics_data') {
        setTotals({ calls: msg.total_calls ?? 0, tokens: msg.total_tokens ?? 0, cost: msg.cost_est ?? 0, days: msg.days ?? 7 });
        setModels(_mapModels(msg.by_model, msg.total_calls ?? 0));
        setReq14d((msg.by_day || []).map((d: any) => d.calls ?? 0));
      }
    } catch {
      // оставляем пусто
    }
  }, [client]);

  useEffect(() => { load(); }, [load]);

  return (
    <ScreenShell>
      <SectionHeader
        title="Метрики LLM"
        subtitle="как Мира думает под капотом · запросы, токены, задержки, расходы"
        actions={
          <div className="flex gap-1.5">
            <ChipToggle>день</ChipToggle>
            <ChipToggle active>{totals.days} дней</ChipToggle>
            <ChipToggle>месяц</ChipToggle>
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto mira-scroll" style={{ padding: '24px 32px 40px' }}>
        {/* KPI row */}
        <div className="flex gap-3 mb-6">
          <Kpi label={`запросов · ${totals.days} дней`} value={totals.calls.toLocaleString('ru-RU')} sub="вызовов LLM за период" />
          <Kpi label="токенов" value={_fmtTokens(totals.tokens)} sub="вход + выход" />
          <Kpi label="ср. задержка" value="—" sub="пока не трекается" />
          <Kpi label="расход" value={`$${totals.cost.toFixed(2)}`} sub={`за ${totals.days} дней`} />
        </div>

        {/* Charts row */}
        <div className="grid grid-cols-[1.7fr_1fr] gap-4 mb-6">
          <div className="p-5 rounded-xl" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(244,234,214,0.10)' }}>
            <div className="flex items-center mb-4">
              <span className="uppercase text-[10px] font-semibold tracking-[0.18em] text-gold">запросы · 14 дней</span>
              <span className="ml-auto text-[11px] text-text-muted font-mono">пик 1 248 · ср 920</span>
            </div>
            <AreaChart data={req14d.length >= 2 ? req14d : [0, 0]} color="#f5bc7a" />
            <div className="flex justify-between mt-2.5 text-[9.5px] text-text-faint font-mono">
              <span>22 мая</span><span>28 мая</span><span>1 июня</span><span>сегодня</span>
            </div>
          </div>

          <div className="p-5 rounded-xl" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(244,234,214,0.10)' }}>
            <div className="uppercase text-[10px] font-semibold tracking-[0.18em] text-gold mb-4">доля моделей</div>
            <div className="flex items-center gap-4">
              <DonutChart models={models} />
              <div className="flex-1 flex flex-col gap-2">
                {models.map((m, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-sm shrink-0" style={{ background: m.color }} />
                    <span className="flex-1 text-[11px] text-text-dim truncate">{m.name}</span>
                    <span className="text-[11px] text-text-primary font-mono">{m.share}%</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Model table */}
        <div className="rounded-xl overflow-hidden mb-6" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(244,234,214,0.10)' }}>
          <div className="px-4 py-3.5" style={{ borderBottom: '1px solid rgba(244,234,214,0.06)' }}>
            <span className="uppercase text-[10px] font-semibold tracking-[0.18em] text-gold">разбивка по моделям</span>
          </div>
          <div className="grid grid-cols-[2fr_1fr_1fr_1fr_1fr] px-4 py-2" style={{ borderBottom: '1px solid rgba(244,234,214,0.06)' }}>
            <span className="text-[10px] text-text-muted tracking-widest uppercase">модель</span>
            <span className="text-[10px] text-text-muted tracking-widest uppercase text-right">запросы</span>
            <span className="text-[10px] text-text-muted tracking-widest uppercase text-right">токены</span>
            <span className="text-[10px] text-text-muted tracking-widest uppercase text-right">ср. задержка</span>
            <span className="text-[10px] text-text-muted tracking-widest uppercase text-right">расход</span>
          </div>
          {models.map((m, i) => (
            <div key={i} className="grid grid-cols-[2fr_1fr_1fr_1fr_1fr] px-4 py-3 items-center" style={{ borderBottom: i < models.length - 1 ? '1px solid rgba(244,234,214,0.06)' : 'none' }}>
              <span className="flex items-center gap-2.5 text-[13px] font-medium" style={{ color: '#f4ead6' }}>
                <span className="w-2 h-2 rounded-sm shrink-0" style={{ background: m.color }} />{m.name}
              </span>
              <span className="text-right text-[12.5px] text-text-dim font-mono">{m.req}</span>
              <span className="text-right text-[12.5px] text-text-dim font-mono">{m.tok}</span>
              <span className="text-right text-[12.5px] text-text-dim font-mono">{m.lat}с</span>
              <span className="text-right text-[12.5px] text-text-dim font-mono">{m.cost}</span>
            </div>
          ))}
        </div>

        {/* Evolve + health */}
        <div className="grid grid-cols-2 gap-4">
          <div
            className="p-5 rounded-xl"
            style={{
              background: 'linear-gradient(135deg, rgba(185,163,255,0.06), rgba(245,188,122,0.04))',
              border: '1px solid rgba(185,163,255,0.20)',
            }}
          >
            <div className="flex items-center gap-2.5 mb-3.5">
              <svg width="18" height="18" viewBox="0 0 16 16" fill="none"><path d="M5 2.5 Q 8 5.5 5 8 Q 2 10.5 5 13.5 M11 2.5 Q 8 5.5 11 8 Q 14 10.5 11 13.5" stroke="#b9a3ff" strokeWidth="1.1" strokeLinecap="round" fill="none"/><circle cx="5" cy="5" r="0.6" fill="#b9a3ff"/><circle cx="11" cy="11" r="0.6" fill="#b9a3ff"/><circle cx="8" cy="8" r="0.6" fill="#b9a3ff"/></svg>
              <span className="uppercase text-[10px] font-semibold tracking-[0.18em]" style={{ color: '#b9a3ff' }}>самоэволюция</span>
            </div>
            <div className="flex gap-6">
              <div>
                <div className="text-[26px] font-mono leading-none" style={{ color: '#f4ead6' }}>0.18.0</div>
                <div className="text-[10.5px] text-text-muted mt-1">текущая версия</div>
              </div>
              <div>
                <div className="text-[26px] font-mono leading-none" style={{ color: '#f4ead6' }}>18</div>
                <div className="text-[10.5px] text-text-muted mt-1">итераций /evolve</div>
              </div>
            </div>
            <div className="mt-3.5 pt-3 font-serif italic text-[11.5px] text-text-dim" style={{ borderTop: '1px solid rgba(185,163,255,0.20)' }}>
              последняя эволюция · 2 июня, 03:14 — «улучшила распознавание времени в напоминаниях»
            </div>
          </div>

          <div className="p-5 rounded-xl" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(244,234,214,0.10)' }}>
            <div className="uppercase text-[10px] font-semibold tracking-[0.18em] text-gold mb-3.5">состояние системы</div>
            <div className="flex flex-col gap-2.5">
              {[
                { l: 'API · доступность', v: '99.8%', ok: true },
                { l: 'ошибки запросов', v: '0.4%', ok: true },
                { l: 'очередь Конклава', v: 'пусто', ok: true },
                { l: 'последний бэкап', v: '4 дня назад', ok: false },
              ].map((r, i) => (
                <div key={i} className="flex items-center gap-2.5">
                  <span className="w-[7px] h-[7px] rounded-full" style={{ background: r.ok ? '#8dd0a7' : '#e88a8a', boxShadow: `0 0 6px ${r.ok ? '#8dd0a7' : '#e88a8a'}` }} />
                  <span className="flex-1 text-[12.5px] text-text-dim">{r.l}</span>
                  <span className="text-[12.5px] text-text-primary font-mono">{r.v}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </ScreenShell>
  );
}
