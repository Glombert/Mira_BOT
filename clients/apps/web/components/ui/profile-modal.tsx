'use client';

import { useState, useEffect, useCallback } from 'react';
import { X, Cloud, Pencil } from 'lucide-react';
import { ModalShell } from './modal-shell';
import type { MiraClient, ProfileData } from '@mira/shared';

const WEB_VERSION = '0.1.0';

const ROLE_LABEL: Record<string, string> = {
  owner: 'Владелец',
  regular: 'Одобрен',
  guest: 'Гость',
  rejected: 'Отклонён',
  blacklisted: 'Чёрный список',
  blocked: 'Заблокирован',
  kid: 'Детский режим',
};

interface Props {
  open: boolean;
  onClose: () => void;
  client: MiraClient | null;
}

export function ProfileModal({ open, onClose, client }: Props) {
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(false);
  const [editingTz, setEditingTz] = useState(false);
  const [tzValue, setTzValue] = useState('');
  const [savingTz, setSavingTz] = useState(false);
  const [forgetMode, setForgetMode] = useState(false);
  const [forgetText, setForgetText] = useState('');

  const load = useCallback(async () => {
    if (!client) return;
    setLoading(true);
    try {
      const msg = await client.sendCommandAwait('profile_data', ['profile_data'], 12000);
      if ('profile' in msg) setProfile(msg.profile);
    } catch {
      /* оставляем как есть */
    } finally {
      setLoading(false);
    }
  }, [client]);

  useEffect(() => {
    if (open) {
      setEditingTz(false);
      setForgetMode(false);
      setForgetText('');
      load();
    }
  }, [open, load]);

  const saveTz = useCallback(async () => {
    if (!client) return;
    setSavingTz(true);
    try {
      await client.sendCommandAwait(`tz ${tzValue.trim()}`, ['system'], 12000);
      await load();
      setEditingTz(false);
    } catch {
      /* no-op */
    } finally {
      setSavingTz(false);
    }
  }, [client, tzValue, load]);

  const doForget = useCallback(() => {
    if (forgetText.trim().toLowerCase() !== 'забудь') return;
    client?.sendCommand('forget');
    onClose();
  }, [client, forgetText, onClose]);

  if (!open) return null;

  const initial = (profile?.name || '?').trim().charAt(0).toUpperCase() || '?';
  const roleLabel = profile ? ROLE_LABEL[profile.role] || profile.role : '';

  return (
    <ModalShell open={open} onClose={onClose}>
      <div className="p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-serif italic text-gold">Профиль</h2>
          <button onClick={onClose} aria-label="Закрыть"
            className="h-8 w-8 flex items-center justify-center rounded-button text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors">
            <X size={18} />
          </button>
        </div>

        {loading && !profile ? (
          <div className="py-10 text-center text-text-muted text-sm">Загрузка…</div>
        ) : !profile ? (
          <div className="py-10 text-center text-text-muted text-sm">Не удалось загрузить профиль</div>
        ) : (
          <div className="space-y-5">
            {/* Hero */}
            <div className="flex flex-col items-center">
              <div className="w-[72px] h-[72px] rounded-full flex items-center justify-center mb-2 bg-gold/10 border border-border-strong">
                <span className="font-serif text-3xl text-gold">{initial}</span>
              </div>
              <div className="font-serif italic text-2xl text-text-primary truncate max-w-full">{profile.name || 'Без имени'}</div>
              <span className="mt-1 px-3 py-0.5 rounded-full bg-gold/10 border border-border-strong text-[11px] tracking-wide text-gold">{roleLabel}</span>
            </div>

            {/* «наша связь» */}
            <div>
              <div className="font-serif italic text-text-secondary mb-2">наша связь</div>
              <div className="grid grid-cols-2 gap-2">
                <Stat value={String(profile.conversations)} label="бесед" mono />
                <Stat value={String(profile.memory_facts)} label="фактов" mono />
                <Stat value={WEB_VERSION} label="версия" mono />
                <Stat value={roleLabel} label="статус" />
              </div>
            </div>

            {/* Наблюдение Миры */}
            {profile.summary ? (
              <div className="rounded-card p-3" style={{ backgroundColor: 'rgba(185,163,255,0.08)', border: '1px solid rgba(185,163,255,0.24)' }}>
                <div className="text-[11px] tracking-wide text-mystic mb-1">✦ что Мира знает о тебе</div>
                <div className="font-serif italic text-sm text-text-primary leading-snug">{profile.summary}</div>
              </div>
            ) : null}

            {/* Личные данные */}
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-text-muted font-semibold mb-1.5">✦ Личные данные</div>
              <div className="rounded-card bg-bg-base border border-border-subtle px-3 divide-y divide-border-divider">
                <Row label="Имя" value={profile.name || '—'} />
                {profile.about_role ? <Row label="Роль" value={profile.about_role} /> : null}
                {profile.about_project ? <Row label="Проект" value={profile.about_project} /> : null}

                {editingTz ? (
                  <div className="flex items-center gap-2 py-2.5">
                    <input
                      value={tzValue}
                      onChange={(e) => setTzValue(e.target.value)}
                      placeholder="Europe/Moscow"
                      autoFocus
                      className="flex-1 bg-bg-surface border border-border-subtle rounded-button px-3 py-1.5 text-sm text-text-primary placeholder:text-text-faint outline-none"
                    />
                    <button onClick={saveTz} disabled={savingTz}
                      className="px-3 py-1.5 rounded-button bg-gold text-bg-base text-sm font-medium disabled:opacity-60">
                      {savingTz ? '…' : 'OK'}
                    </button>
                    <button onClick={() => setEditingTz(false)} className="text-text-muted hover:text-text-primary"><X size={16} /></button>
                  </div>
                ) : (
                  <button onClick={() => { setTzValue(profile.timezone || ''); setEditingTz(true); }}
                    className="w-full flex items-center py-2.5 text-left group">
                    <span className="text-sm text-text-secondary">Часовой пояс</span>
                    <span className="ml-auto text-sm text-text-primary truncate">{profile.timezone || 'не задан'}</span>
                    <Pencil size={13} className="ml-2 text-gold shrink-0" />
                  </button>
                )}

                {profile.telegram ? <Row label="Telegram" value={profile.telegram} /> : null}
                <Row label="ID" value={profile.id} mono />
              </div>
            </div>

            {/* Интеграции */}
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-text-muted font-semibold mb-1.5">✦ Интеграции</div>
              <div className="rounded-card bg-bg-base border border-border-subtle px-3">
                <div className="flex items-center py-2.5">
                  <Cloud size={16} className="text-text-secondary" />
                  <span className="ml-2 text-sm text-text-secondary">Google Drive</span>
                  <span className="ml-auto flex items-center gap-1.5">
                    {profile.gdrive_linked && <span className="w-1.5 h-1.5 rounded-full bg-sage" />}
                    <span className={`text-sm truncate ${profile.gdrive_linked ? 'text-sage' : 'text-text-primary'}`}>
                      {profile.gdrive_linked ? (profile.gdrive_email || 'подключено') : 'не подключено'}
                    </span>
                  </span>
                </div>
              </div>
            </div>

            {/* Опасная зона */}
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-rose font-semibold mb-1.5">⚠ Опасная зона</div>
              {!forgetMode ? (
                <button onClick={() => setForgetMode(true)}
                  className="w-full py-2.5 rounded-button border text-rose font-medium transition-colors"
                  style={{ borderColor: 'rgba(232,138,138,0.4)', backgroundColor: 'rgba(232,138,138,0.08)' }}>
                  Забыть меня
                </button>
              ) : (
                <div className="rounded-card p-3" style={{ border: '1px solid rgba(232,138,138,0.4)', backgroundColor: 'rgba(232,138,138,0.06)' }}>
                  <div className="text-sm text-text-primary mb-2">Мира удалит профиль, историю и всё, что запомнила. Необратимо. Введите <b className="text-rose">забудь</b> для подтверждения.</div>
                  <div className="flex items-center gap-2">
                    <input value={forgetText} onChange={(e) => setForgetText(e.target.value)} placeholder="забудь" autoFocus
                      className="flex-1 bg-bg-surface border border-border-subtle rounded-button px-3 py-1.5 text-sm text-text-primary placeholder:text-text-faint outline-none" />
                    <button onClick={doForget} disabled={forgetText.trim().toLowerCase() !== 'забудь'}
                      className="px-3 py-1.5 rounded-button text-bg-base text-sm font-medium disabled:opacity-40"
                      style={{ backgroundColor: '#e88a8a' }}>
                      Удалить
                    </button>
                    <button onClick={() => { setForgetMode(false); setForgetText(''); }} className="text-text-muted hover:text-text-primary"><X size={16} /></button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </ModalShell>
  );
}

function Stat({ value, label, mono }: { value: string; label: string; mono?: boolean }) {
  return (
    <div className="bg-bg-base border border-border-subtle rounded-card py-3 flex flex-col items-center">
      <span className={`text-gold ${mono ? 'font-mono text-lg' : 'text-base'} truncate max-w-full px-1`}>{value}</span>
      <span className="text-[10px] text-text-muted mt-0.5 tracking-wide">{label}</span>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center py-2.5">
      <span className="text-sm text-text-secondary">{label}</span>
      <span className={`ml-auto text-sm text-text-primary truncate ${mono ? 'font-mono text-xs' : ''}`}>{value}</span>
    </div>
  );
}
