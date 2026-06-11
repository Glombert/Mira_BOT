'use client';

import React, { useState, useEffect, useCallback } from 'react';
import type { MiraClient } from '@mira/shared';
import { SectionHeader, ChipToggle, ScreenShell } from './screen-primitives';
import { AreaChart, Kpi } from './metrics-screen';

type VpnStats = Extract<
  import('@mira/shared').ServerMessage,
  { type: 'vpn_stats_data' }
>;

function _fmtMb(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${Math.round(mb)} MB`;
}

function _fmtMinutes(min: number): string {
  if (min >= 60) return `${Math.floor(min / 60)} ч ${min % 60} м`;
  return `${min} м`;
}

function _lastSeen(min: number | null): string {
  if (min == null || Number.isNaN(min)) return 'не подключался';
  if (min < 3) return 'сейчас';
  if (min < 60) return `${min} мин назад`;
  if (min < 1440) return `${Math.round(min / 60)} ч назад`;
  return `${Math.round(min / 1440)} дн назад`;
}

// Цвет на каждое устройство — стабильно по индексу.
const _PEER_COLORS = ['#f5bc7a', '#8dd0a7', '#b9a3ff', '#7aa6f5', '#e88a8a', '#e0c068', '#6fd0c8', '#d98ec4'];
const _peerColor = (i: number) => _PEER_COLORS[i % _PEER_COLORS.length];

// Кольцо долей трафика по устройствам + общий объём в центре.
function TrafficDonut({ slices, total, size = 132 }: {
  slices: { value: number; color: string }[]; total: string; size?: number;
}) {
  const r = size / 2 - 9;
  const cx = size / 2, cy = size / 2;
  const circ = 2 * Math.PI * r;
  const sum = slices.reduce((s, x) => s + x.value, 0) || 1;
  let offset = 0;
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="11" />
        {slices.map((s, i) => {
          const len = (s.value / sum) * circ;
          const el = (
            <circle key={i} cx={cx} cy={cy} r={r} fill="none" stroke={s.color} strokeWidth="11"
              strokeDasharray={`${len} ${circ - len}`} strokeDashoffset={-offset} strokeLinecap="butt" />
          );
          offset += len;
          return el;
        })}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-[10px] uppercase tracking-[0.16em] text-text-muted">всего</span>
        <span className="text-base font-mono text-text-primary">{total}</span>
      </div>
    </div>
  );
}

// Мультилинейный график трафика: линия на каждое устройство своим цветом,
// оси время × объём, сетка, лёгкая заливка (Grafana-стиль).
function MultiLineChart({ series, lines, labels }: {
  series: { ts: string; users: Record<string, number> }[];
  lines: { name: string; color: string }[];
  labels: string[];
}) {
  const w = 600, h = 150, padL = 4, padR = 4;
  const innerW = w - padL - padR;
  const n = series.length;
  let max = 0;
  for (const s of series) for (const l of lines) max = Math.max(max, s.users[l.name] || 0);
  max = max * 1.15 || 1;
  const stepX = n > 1 ? innerW / (n - 1) : 0;
  const x = (i: number) => padL + i * stepX;
  const y = (v: number) => h - (v / max) * h;
  const yTicks = [0, max / 2, max];
  const fmt = (mb: number) => (mb >= 1024 ? `${(mb / 1024).toFixed(1)}G` : `${Math.round(mb)}M`);

  return (
    <div>
      <svg width="100%" height={h + 18} viewBox={`0 0 ${w} ${h + 18}`} preserveAspectRatio="none"
           style={{ display: 'block', overflow: 'visible' }}>
        <defs>
          {lines.map((l, i) => (
            <linearGradient key={i} id={`vpnfill-${i}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={l.color} stopOpacity="0.18" />
              <stop offset="100%" stopColor={l.color} stopOpacity="0" />
            </linearGradient>
          ))}
        </defs>
        {/* сетка + Y-метки */}
        {yTicks.map((t, i) => (
          <g key={i}>
            <line x1={padL} y1={y(t)} x2={w - padR} y2={y(t)} stroke="rgba(244,234,214,0.07)" strokeWidth="1" />
            <text x={padL} y={y(t) - 3} fill="rgba(244,234,214,0.35)" fontSize="9" fontFamily="monospace">{fmt(t)}</text>
          </g>
        ))}
        {/* линии устройств */}
        {n >= 2 && lines.map((l, li) => {
          const pts = series.map((s, i) => `${x(i)},${y(s.users[l.name] || 0)}`);
          const line = `M ${pts.join(' L ')}`;
          const area = `${line} L ${x(n - 1)},${h} L ${x(0)},${h} Z`;
          return (
            <g key={li}>
              <path d={area} fill={`url(#vpnfill-${li})`} />
              <path d={line} fill="none" stroke={l.color} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" />
            </g>
          );
        })}
      </svg>
      <div className="flex justify-between mt-1 text-[9.5px] text-text-faint font-mono">
        {labels.map((l, i) => <span key={i}>{l}</span>)}
      </div>
    </div>
  );
}

function ChartCard({ title, note, data, color, labels }: {
  title: string; note: string; data: number[]; color: string; labels: string[];
}) {
  return (
    <div className="p-5 rounded-xl" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(244,234,214,0.10)' }}>
      <div className="flex items-center mb-4">
        <span className="uppercase text-[10px] font-semibold tracking-[0.18em] text-gold">{title}</span>
        <span className="ml-auto text-[11px] text-text-muted font-mono">{note}</span>
      </div>
      <AreaChart data={data.length >= 2 ? data : [0, 0]} color={color} />
      <div className="flex justify-between mt-2.5 text-[9.5px] text-text-faint font-mono">
        {labels.map((l, i) => <span key={i}>{l}</span>)}
      </div>
    </div>
  );
}

export function VpnScreen({ client }: { client: MiraClient | null }) {
  const [stats, setStats] = useState<VpnStats | null>(null);
  const [hours, setHours] = useState(24);

  const load = useCallback(async (h: number) => {
    if (!client) return;
    try {
      const msg = await client.sendCommandAwait(`vpn_stats ${h}`, ['vpn_stats_data'], 15000);
      if (msg && msg.type === 'vpn_stats_data') setStats(msg);
    } catch {
      // мост может отвечать до 4с — оставляем прошлое состояние
    }
  }, [client]);

  useEffect(() => { load(hours); }, [load, hours]);

  const pts = stats?.points ?? [];
  const traffic = pts.map((p) => p.rx_mb + p.tx_mb);
  const latency = (stats?.bridge_points ?? []).map((p) => p.latency_ms ?? 0);
  const totalMb = (stats?.peers ?? []).reduce((s, p) => s + p.rx_mb + p.tx_mb, 0);
  const periodLabel = hours === 24 ? '24 часа' : '7 дней';
  const labels = pts.length >= 2 ? (() => {
    const fmt = (iso: string) => {
      const d = new Date(iso);
      return hours > 48
        ? d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
        : d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
    };
    return [fmt(pts[0].ts), fmt(pts[Math.floor(pts.length / 2)].ts), 'сейчас'];
  })() : [];

  return (
    <ScreenShell>
      <SectionHeader
        title="VPN"
        subtitle="мост и WireGuard · кто подключён, сколько сидит, сколько качает"
        actions={
          <div className="flex gap-1.5">
            <ChipToggle active={hours === 24} onClick={() => setHours(24)}>24 часа</ChipToggle>
            <ChipToggle active={hours === 168} onClick={() => setHours(168)}>7 дней</ChipToggle>
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto mira-scroll" style={{ padding: '24px 32px 40px' }}>
        {/* Состояние — цифрами */}
        <div className="flex gap-3 mb-6">
          <Kpi label="РУ-мост" value={stats ? (stats.bridge_ok ? 'жив' : 'НЕ ОТВЕЧАЕТ') : '—'}
               sub={stats?.bridge_latency_ms != null ? `пинг ${stats.bridge_latency_ms} мс` : 'TCP-проверка'} />
          <Kpi label="WireGuard" value={stats ? (stats.wg_up ? 'жив' : 'ЛЕЖИТ') : '—'}
               sub="интерфейс wg0 · Амстердам" />
          <Kpi label="онлайн" value={stats ? `${stats.peers_online}` : '—'}
               sub={`из ${stats?.peers.length ?? 0} устройств`} />
          <Kpi label="трафик" value={stats ? _fmtMb(totalMb) : '—'} sub={`за ${periodLabel} · ↓+↑`} />
        </div>

        {/* Трафик по устройствам — мультилинейный график */}
        <div className="p-5 rounded-xl mb-4" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(244,234,214,0.10)' }}>
          <div className="flex items-center mb-3">
            <span className="uppercase text-[10px] font-semibold tracking-[0.18em] text-gold">трафик по устройствам · {periodLabel}</span>
          </div>
          <MultiLineChart
            series={stats?.traffic_series ?? []}
            lines={(stats?.peers ?? []).map((p, i) => ({ name: p.name, color: _peerColor(i) }))}
            labels={labels}
          />
          {/* легенда цветов */}
          <div className="flex flex-wrap gap-x-4 gap-y-1.5 mt-3">
            {(stats?.peers ?? []).map((p, i) => (
              <span key={i} className="inline-flex items-center gap-1.5 text-[11px] text-text-dim">
                <span className="w-2.5 h-2.5 rounded-sm" style={{ background: _peerColor(i) }} />
                {p.name}
              </span>
            ))}
          </div>
        </div>

        {/* Пинг моста */}
        <div className="mb-6">
          <ChartCard title={`пинг моста · ${periodLabel}`}
                     note={`пик ${latency.length ? Math.max(...latency) : 0} мс`}
                     data={latency} color="#7aa6f5" labels={labels} />
        </div>

        {/* Доли трафика по устройствам — цветами */}
        {(stats?.peers ?? []).some((p) => p.rx_mb + p.tx_mb > 0) && (
          <div className="p-5 mb-6 rounded-xl flex items-center gap-6" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(244,234,214,0.10)' }}>
            <TrafficDonut
              total={_fmtMb(totalMb)}
              slices={(stats?.peers ?? []).map((p, i) => ({ value: p.rx_mb + p.tx_mb, color: _peerColor(i) }))}
            />
            <div className="flex-1 grid grid-cols-2 gap-x-6 gap-y-2">
              {(stats?.peers ?? []).map((p, i) => {
                const v = p.rx_mb + p.tx_mb;
                const pct = totalMb ? Math.round((v / totalMb) * 100) : 0;
                return (
                  <div key={i} className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: _peerColor(i) }} />
                    <span className="flex-1 text-[12px] text-text-dim truncate">{p.name}</span>
                    <span className="text-[11px] font-mono text-text-muted">{_fmtMb(v)}</span>
                    <span className="text-[11px] font-mono text-text-primary w-9 text-right">{pct}%</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Устройства */}
        <div className="rounded-xl overflow-hidden" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(244,234,214,0.10)' }}>
          <div className="px-5 pt-4 pb-3 uppercase text-[10px] font-semibold tracking-[0.18em] text-gold">
            устройства · {periodLabel}
          </div>
          <table className="w-full text-[12.5px]">
            <thead>
              <tr className="text-left text-[10px] uppercase tracking-[0.14em] text-text-muted">
                <th className="px-5 py-2 font-semibold">имя</th>
                <th className="px-3 py-2 font-semibold">статус</th>
                <th className="px-3 py-2 font-semibold text-right">в сети</th>
                <th className="px-3 py-2 font-semibold text-right">скачано ↓</th>
                <th className="px-5 py-2 font-semibold text-right">отдано ↑</th>
              </tr>
            </thead>
            <tbody>
              {(stats?.peers ?? []).map((p, i) => (
                <tr key={i} style={{ borderTop: '1px solid rgba(244,234,214,0.06)' }}>
                  <td className="px-5 py-2.5 text-text-primary">
                    <span className="inline-flex items-center gap-2">
                      <span className="w-2.5 h-2.5 rounded-sm shrink-0" style={{ background: _peerColor(i) }} />
                      {p.name}
                      <span className="text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded"
                            style={{ background: 'rgba(244,234,214,0.06)', color: 'var(--text-muted, #9a9384)' }}>
                        {p.kind === 'reality' ? 'Reality' : 'WG'}
                      </span>
                    </span>
                  </td>
                  <td className="px-3 py-2.5">
                    <span className="inline-flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full" style={{ background: p.online ? '#8dd0a7' : 'rgba(244,234,214,0.25)' }} />
                      <span className={p.online ? 'text-text-primary' : 'text-text-muted'}>
                        {p.online ? 'онлайн' : _lastSeen(p.last_seen_min)}
                      </span>
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono text-text-dim">{_fmtMinutes(p.online_minutes)}</td>
                  <td className="px-3 py-2.5 text-right font-mono text-text-dim">{_fmtMb(p.rx_mb)}</td>
                  <td className="px-5 py-2.5 text-right font-mono text-text-dim">{_fmtMb(p.tx_mb)}</td>
                </tr>
              ))}
              {!stats?.peers.length && (
                <tr><td colSpan={5} className="px-5 py-4 text-text-muted">Нет данных — сэмплы копятся раз в 5 минут.</td></tr>
              )}
            </tbody>
          </table>
        </div>

        <div className="mt-4 text-[12px] text-text-muted">
          Новое устройство = свой WireGuard-пир: на сервере <span className="font-mono">scripts/wg_add_peer.sh имя</span> — выдаст конфиг и QR.
        </div>
      </div>
    </ScreenShell>
  );
}
