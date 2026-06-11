'use client';

import React, { useState, useEffect, useCallback } from 'react';
import type { MiraClient } from '@mira/shared';
import { SectionHeader, ChipToggle, ScreenShell } from './screen-primitives';
import { AreaChart, Kpi } from './metrics-screen';

type ServerStats = Extract<
  import('@mira/shared').ServerMessage,
  { type: 'server_stats_data' }
>;

function _hbText(age: number | null): { value: string; ok: boolean } {
  if (age === null) return { value: 'нет', ok: false };
  if (age <= 120) return { value: 'жив', ok: true };
  return { value: `${Math.round(age / 60)} мин назад`, ok: false };
}

function _axisLabels(points: ServerStats['points'], hours: number): string[] {
  if (points.length < 2) return [];
  const fmt = (iso: string) => {
    const d = new Date(iso);
    return hours > 48
      ? d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
      : d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  };
  const mid = points[Math.floor(points.length / 2)];
  return [fmt(points[0].ts), fmt(mid.ts), 'сейчас'];
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

export function ServerScreen({ client }: { client: MiraClient | null }) {
  const [stats, setStats] = useState<ServerStats | null>(null);
  const [hours, setHours] = useState(24);

  const load = useCallback(async (h: number) => {
    if (!client) return;
    try {
      const msg = await client.sendCommandAwait(`server_stats ${h}`, ['server_stats_data'], 12000);
      if (msg && msg.type === 'server_stats_data') setStats(msg);
    } catch {
      // сервер недоступен — оставляем прошлые данные
    }
  }, [client]);

  useEffect(() => { load(hours); }, [load, hours]);

  const pts = stats?.points ?? [];
  const memSeries = pts.map((p) => p.mem_percent);
  const loadSeries = pts.map((p) => p.load1);
  const labels = _axisLabels(pts, hours);
  const hbBot = _hbText(stats?.hb_bot_age ?? null);
  const hbWeb = _hbText(stats?.hb_web_age ?? null);
  const memMax = memSeries.length ? Math.max(...memSeries) : 0;
  const loadMax = loadSeries.length ? Math.max(...loadSeries) : 0;

  return (
    <ScreenShell>
      <SectionHeader
        title="Сервер"
        subtitle="дом Миры · RAM, нагрузка, диск, heartbeat — живые и за период"
        actions={
          <div className="flex gap-1.5">
            <ChipToggle active={hours === 24} onClick={() => setHours(24)}>24 часа</ChipToggle>
            <ChipToggle active={hours === 168} onClick={() => setHours(168)}>7 дней</ChipToggle>
          </div>
        }
      />

      <div className="flex-1 overflow-y-auto mira-scroll" style={{ padding: '24px 32px 40px' }}>
        {/* Текущее состояние — цифрами */}
        <div className="flex gap-3 mb-3">
          <Kpi label="RAM" value={stats ? `${stats.mem_percent}` : '—'} unit="%"
               sub={stats ? `из ${(stats.mem_total_mb / 1024).toFixed(1)} GB${stats.swap_mb > 0 ? ` · swap ${stats.swap_mb} MB` : ''}` : ''} />
          <Kpi label="нагрузка CPU" value={stats ? stats.load1.toFixed(2) : '—'} sub="load average · 1 мин" />
          <Kpi label="диск" value={stats ? `${stats.disk_free_gb}` : '—'} unit="GB"
               sub={stats ? `свободно из ${stats.disk_total_gb} GB` : ''} />
        </div>
        <div className="flex gap-3 mb-6">
          <Kpi label="heartbeat · бот" value={hbBot.value} sub={hbBot.ok ? 'отвечает' : 'проверь systemd'} />
          <Kpi label="heartbeat · веб" value={hbWeb.value} sub={hbWeb.ok ? 'отвечает' : 'проверь systemd'} />
          <Kpi label="mira.db" value={stats ? `${stats.db_size_mb}` : '—'} unit="MB" sub="память Миры" />
          <Kpi label="аптайм" value={stats ? `${stats.uptime_days}` : '—'} unit="дн" sub="с перезагрузки сервера" />
        </div>

        {/* Динамика — графиками */}
        <div className="grid grid-cols-2 gap-4">
          <ChartCard title={`RAM · ${hours === 24 ? '24 часа' : '7 дней'}`}
                     note={`пик ${memMax}%`} data={memSeries} color="#f5bc7a" labels={labels} />
          <ChartCard title={`нагрузка · ${hours === 24 ? '24 часа' : '7 дней'}`}
                     note={`пик ${loadMax.toFixed(2)}`} data={loadSeries} color="#8dd0a7" labels={labels} />
        </div>
        {pts.length < 2 && (
          <div className="mt-4 text-[12px] text-text-muted">
            Сэмплы копятся раз в 5 минут — графики наполнятся в течение часа после запуска.
          </div>
        )}
      </div>
    </ScreenShell>
  );
}
