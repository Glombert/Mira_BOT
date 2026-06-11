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
  if (min === null) return 'не подключался';
  if (min < 3) return 'сейчас';
  if (min < 60) return `${min} мин назад`;
  if (min < 1440) return `${Math.round(min / 60)} ч назад`;
  return `${Math.round(min / 1440)} дн назад`;
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

        {/* Динамика — графиками */}
        <div className="grid grid-cols-2 gap-4 mb-6">
          <ChartCard title={`трафик · ${periodLabel}`}
                     note={`пик ${_fmtMb(traffic.length ? Math.max(...traffic) : 0)} / 5 мин`}
                     data={traffic} color="#f5bc7a" labels={labels} />
          <ChartCard title={`пинг моста · ${periodLabel}`}
                     note={`пик ${latency.length ? Math.max(...latency) : 0} мс`}
                     data={latency} color="#7aa6f5" labels={labels} />
        </div>

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
                    {p.name}
                    <span className="ml-2 text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded"
                          style={{ background: 'rgba(244,234,214,0.06)', color: 'var(--text-muted, #9a9384)' }}>
                      {p.kind === 'reality' ? 'Reality' : 'WG'}
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
