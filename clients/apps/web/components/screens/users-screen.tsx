'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { SectionHeader, ScreenShell } from './screen-primitives';
import type { MiraClient, UserEntry } from '@mira/shared';

const STATUS_LABEL: Record<string, string> = {
  owner: 'Владелец', regular: 'Одобрен', guest: 'Гость',
  rejected: 'Отклонён', blacklisted: 'Чёрный список', blocked: 'Блок',
};

const STATUS_COLOR: Record<string, string> = {
  owner: '#f5bc7a', regular: '#8dd0a7', guest: 'rgba(244,234,214,0.62)',
  rejected: '#e88a8a', blacklisted: '#e88a8a', blocked: '#e88a8a',
};

interface UsersScreenProps {
  client: MiraClient | null;
}

export function UsersScreen({ client }: UsersScreenProps) {
  const [users, setUsers] = useState<UserEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [openUserId, setOpenUserId] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!client) return;
    setLoading(true);
    try {
      const msg = await client.sendCommandAwait('users_data', ['users_list'], 8000);
      if ('users' in msg && Array.isArray(msg.users)) {
        setUsers(msg.users);
      }
    } catch {
      setUsers([]);
    } finally {
      setLoading(false);
    }
  }, [client]);

  useEffect(() => {
    load();
  }, [load]);

  const handleAction = (cmd: string) => {
    if (!client) return;
    client.sendCommand(cmd);
    setOpenUserId(null);
    setTimeout(load, 600);
  };

  return (
    <ScreenShell>
      <SectionHeader
        title="Пользователи"
        subtitle="кто имеет доступ к Мире · одобрение, блокировка, роли"
      />

      <div className="flex-1 overflow-y-auto mira-scroll" style={{ padding: '24px 32px 40px' }}>
        {loading ? (
          <div className="text-center text-text-muted text-sm py-10">Загрузка…</div>
        ) : users.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-text-muted">
            <svg width="48" height="48" viewBox="0 0 28 28" fill="none">
              <defs>
                <linearGradient id="emptyUsers" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#f5bc7a" stopOpacity="0.3" />
                  <stop offset="1" stopColor="#f8cfa0" stopOpacity="0.2" />
                </linearGradient>
              </defs>
              <circle cx="14" cy="10" r="5" fill="url(#emptyUsers)" />
              <ellipse cx="14" cy="24" rx="8" ry="4" fill="url(#emptyUsers)" />
            </svg>
            <p className="text-sm text-text-secondary font-serif italic">Пока нет пользователей</p>
          </div>
        ) : (
          <div className="space-y-1">
            {users.map((u) => {
              const isOpen = openUserId === u.id;
              return (
                <div
                  key={u.id}
                  className="rounded-xl"
                  style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(244,234,214,0.10)' }}
                >
                  <button
                    onClick={() => setOpenUserId(isOpen ? null : u.id)}
                    className="w-full flex items-center justify-between px-4 py-3 text-left"
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className="w-9 h-9 rounded-full flex items-center justify-center font-serif text-lg"
                        style={{ background: 'linear-gradient(135deg, #f5bc7a, #b9a3ff)', color: '#070c1c' }}
                      >
                        {(u.name || '?').charAt(0).toUpperCase()}
                      </div>
                      <div>
                        <div className="text-sm font-medium" style={{ color: '#f4ead6' }}>{u.name || u.id}</div>
                        <div className="text-[11px] font-mono text-text-muted">{u.id}</div>
                      </div>
                    </div>
                    <span
                      className="text-[10px] font-mono px-2 py-0.5 rounded-full shrink-0"
                      style={{
                        background: `${STATUS_COLOR[u.status] || 'rgba(244,234,214,0.62)'}15`,
                        color: STATUS_COLOR[u.status] || 'rgba(244,234,214,0.62)',
                        border: `1px solid ${STATUS_COLOR[u.status] || 'rgba(244,234,214,0.10)'}30`,
                      }}
                    >
                      {STATUS_LABEL[u.status] || u.status}
                    </span>
                  </button>
                  {isOpen && (
                    <div className="px-4 pb-3 flex gap-2">
                      <button
                        onClick={() => handleAction(`approve ${u.id}`)}
                        className="px-3 py-1.5 rounded-md text-xs bg-sage/20 text-sage hover:bg-sage/30 transition-colors"
                      >
                        Одобрить
                      </button>
                      <button
                        onClick={() => handleAction(`reject ${u.id}`)}
                        className="px-3 py-1.5 rounded-md text-xs bg-gold/10 text-gold hover:bg-gold/20 transition-colors"
                      >
                        Отклонить
                      </button>
                      <button
                        onClick={() => handleAction(`block ${u.id}`)}
                        className="px-3 py-1.5 rounded-md text-xs bg-rose/20 text-rose hover:bg-rose/30 transition-colors"
                      >
                        Заблокировать
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </ScreenShell>
  );
}
