'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { SectionHeader, ScreenShell } from './screen-primitives';
import type { MiraClient } from '@mira/shared';

interface Task {
  id: string;
  title: string;
  status: 'todo' | 'done' | 'deferred';
  due?: string;
}

interface TasksScreenProps {
  client: MiraClient | null;
}

export function TasksScreen({ client }: TasksScreenProps) {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!client) return;
    setLoading(true);
    try {
      const msg = await client.sendCommandAwait('tasks', ['system', 'message'], 8000);
      // TODO: parse structured tasks when backend supports tasks_data
      setTasks([]);
    } catch {
      setTasks([]);
    } finally {
      setLoading(false);
    }
  }, [client]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <ScreenShell>
      <SectionHeader
        title="Задачи"
        subtitle="что Мира держит для тебя · отложенное, важное, сроки"
      />

      <div className="flex-1 overflow-y-auto mira-scroll" style={{ padding: '24px 32px 40px' }}>
        {loading ? (
          <div className="text-center text-text-muted text-sm py-10">Загрузка…</div>
        ) : tasks.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-text-muted">
            <svg width="48" height="48" viewBox="0 0 28 28" fill="none">
              <defs>
                <linearGradient id="emptyTasks" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#f5bc7a" stopOpacity="0.3" />
                  <stop offset="1" stopColor="#f8cfa0" stopOpacity="0.2" />
                </linearGradient>
              </defs>
              <rect x="5" y="5" width="18" height="18" rx="2" fill="url(#emptyTasks)" />
              <path d="M9 14 L12 17 L19 10" stroke="#0b1226" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <p className="text-sm text-text-secondary font-serif italic">Нет активных задач</p>
          </div>
        ) : (
          <div className="space-y-2">
            {tasks.map((t) => (
              <div
                key={t.id}
                className="flex items-center gap-3 px-4 py-3 rounded-xl"
                style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(244,234,214,0.10)' }}
              >
                <div
                  className="w-5 h-5 rounded border flex items-center justify-center shrink-0"
                  style={{
                    borderColor: t.status === 'done' ? '#8dd0a7' : 'rgba(244,234,214,0.20)',
                    background: t.status === 'done' ? '#8dd0a7' : 'transparent',
                  }}
                >
                  {t.status === 'done' && (
                    <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M3.5 8.5 L6.5 11.5 L12.5 5" stroke="#0b1226" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/></svg>
                  )}
                </div>
                <div className="flex-1">
                  <div className={`text-sm ${t.status === 'done' ? 'line-through text-text-muted' : 'text-text-primary'}`}>{t.title}</div>
                  {t.due && <div className="text-[11px] text-text-muted font-mono mt-0.5">{t.due}</div>}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </ScreenShell>
  );
}
