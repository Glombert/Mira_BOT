'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Cloud } from 'lucide-react';
import { SectionHeader, FormRow, ChipToggle, PrefRow, EditPen, ScreenShell } from './screen-primitives';
import { Spark } from '../chat/aurora-cards';
import { TIMEZONES } from '@/lib/timezones';
import type { MiraClient, ProfileData } from '@mira/shared';

const ROLE_LABEL: Record<string, string> = {
  owner: 'Владелец', regular: 'Одобрен', guest: 'Гость',
  rejected: 'Отклонён', blacklisted: 'Чёрный список', blocked: 'Заблокирован', kid: 'Детский режим',
};

const MANNER_FALLBACK = ['тёплая', 'вдумчивая', 'немногословная', 'игривая', 'формальная', 'дерзкая', 'заботливая', 'прямая'];

interface ProfileScreenProps {
  client: MiraClient | null;
}

export function ProfileScreen({ client }: ProfileScreenProps) {
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState(false);

  const [addressing, setAddressing] = useState('');
  const [addressForm, setAddressForm] = useState('');
  const [manner, setManner] = useState<string[]>([]);
  const [origin, setOrigin] = useState('');
  const [occupation, setOccupation] = useState('');
  const [notes, setNotes] = useState('');
  const [timezone, setTimezone] = useState('');
  const [confirmForget, setConfirmForget] = useState(false);
  const [forgotten, setForgotten] = useState(false);

  const load = useCallback(async () => {
    if (!client) return;
    setLoading(true);
    try {
      const msg = await client.sendCommandAwait('profile_data', ['profile_data'], 12000);
      if ('profile' in msg) {
        const p = msg.profile;
        setProfile(p);
        setAddressing(p.addressing || p.name || '');
        setAddressForm(p.address_form || '');
        setManner(p.manner || []);
        setOrigin(p.origin || '');
        setOccupation(p.occupation || '');
        setNotes(p.notes || '');
        setTimezone(p.timezone || '');
      }
    } catch {
      /* no-op */
    } finally {
      setLoading(false);
    }
  }, [client]);

  useEffect(() => {
    load();
  }, [load]);

  const toggleManner = (m: string) => setManner((prev) => (prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m]));

  const save = useCallback(() => {
    if (!client) return;
    client.saveProfile({
      addressing: addressing.trim(), address_form: addressForm, manner,
      origin: origin.trim(), occupation: occupation.trim(), notes: notes.trim(),
      timezone: timezone.trim(),
    });
    setEditing(false);
    setTimeout(load, 300);
  }, [client, addressing, addressForm, manner, origin, occupation, notes, timezone, load]);

  const forget = useCallback(() => {
    if (!client) return;
    client.sendCommand('forget');
    setConfirmForget(false);
    setForgotten(true);
    setProfile(null);
  }, [client]);

  if (loading && !profile) {
    return (
      <ScreenShell>
        <SectionHeader title="Профиль" />
        <div className="flex-1 flex items-center justify-center text-text-muted text-sm">Загрузка…</div>
      </ScreenShell>
    );
  }

  const initial = (addressing || profile?.name || '?').trim().charAt(0).toUpperCase() || '?';
  const roleLabel = profile ? ROLE_LABEL[profile.role] || profile.role : '';
  const mannerOptions = profile?.manner_options?.length ? profile.manner_options : MANNER_FALLBACK;

  const stats = [
    { label: 'мы вместе', value: String(profile?.days_together ?? 0), unit: 'дней' },
    { label: 'диалогов', value: String(profile?.conversations ?? 0), unit: '' },
    { label: 'фактов в памяти', value: String(profile?.memory_facts ?? 0), unit: '' },
    { label: 'версия Миры', value: '0.18.0', unit: '', mono: true },
  ];

  return (
    <ScreenShell>
      <SectionHeader
        title="Профиль"
        subtitle="как Мира видит тебя · и как ты хочешь, чтобы она тебя видела"
        actions={
          !editing ? (
            <button
              onClick={() => setEditing(true)}
              className="inline-flex items-center gap-2 h-9 px-4 text-xs font-medium tracking-wide rounded-lg transition-colors hover:bg-white/[0.04]"
              style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(244,234,214,0.10)', color: '#f4ead6' }}
            >
              <EditPen /> редактировать
            </button>
          ) : (
            <button
              onClick={save}
              className="inline-flex items-center gap-2 h-9 px-4 text-xs font-medium tracking-wide rounded-lg transition-colors"
              style={{ background: '#f5bc7a', color: '#070c1c' }}
            >
              Сохранить
            </button>
          )
        }
      />

      <div className="flex-1 overflow-y-auto mira-scroll" style={{ padding: '28px 32px 40px' }}>
        {/* Hero band: avatar + bond */}
        <div
          className="flex gap-7 items-start pb-7 mb-6"
          style={{ borderBottom: '1px solid rgba(244,234,214,0.06)' }}
        >
          {/* User avatar card */}
          <div
            className="w-60 p-5 rounded-[14px] relative overflow-hidden flex flex-col items-center gap-3.5 text-center"
            style={{
              background: 'linear-gradient(160deg, rgba(245,188,122,0.08), rgba(185,163,255,0.06))',
              border: '1px solid rgba(244,234,214,0.10)',
            }}
          >
            <div
              className="mira-breathe absolute top-3 left-1/2 -translate-x-1/2 w-[100px] h-[100px] rounded-full"
              style={{
                background: 'radial-gradient(circle, rgba(245,188,122,0.55) 0%, transparent 70%)',
                opacity: 0.5,
              }}
            />
            <div
              className="relative z-[1] w-[72px] h-[72px] rounded-full flex items-center justify-center font-serif text-4xl font-medium"
              style={{
                background: 'linear-gradient(135deg, #f5bc7a, #b9a3ff)',
                color: '#070c1c',
              }}
            >
              {initial}
            </div>
            <div className="relative z-[1]">
              <div className="font-serif italic text-2xl" style={{ color: '#f4ead6', lineHeight: 1.1 }}>
                {addressing || profile?.name || 'Без имени'}
              </div>
              <div className="text-[11px] mt-1 tracking-widest" style={{ color: '#f5bc7a' }}>
                {roleLabel} · с {profile ? new Date(Date.now() - (profile.days_together || 0) * 86400000).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' }) : '...'}
              </div>
            </div>
          </div>

          {/* Bond stats */}
          <div className="flex-1 min-w-0">
            <div className="uppercase text-[10px] font-semibold tracking-[0.18em] text-text-muted mb-3">
              наша связь
            </div>
            <div className="grid grid-cols-4 gap-3">
              {stats.map((s, i) => (
                <div
                  key={i}
                  className="p-3.5 rounded-[10px]"
                  style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(244,234,214,0.10)' }}
                >
                  <div
                    className="text-[28px] leading-none mb-1"
                    style={{
                      color: '#f4ead6',
                      fontFamily: s.mono ? '"JetBrains Mono", monospace' : undefined,
                      fontStyle: s.mono ? 'normal' : 'normal',
                      letterSpacing: s.mono ? '-0.02em' : 0,
                    }}
                  >
                    {s.value}
                  </div>
                  {s.unit && (
                    <span className="text-[11px] text-gold/70 font-mono ml-1">{s.unit}</span>
                  )}
                  <div className="text-[11px] text-text-muted mt-1 tracking-wide">{s.label}</div>
                </div>
              ))}
            </div>

            {/* Poetic stat */}
            <div
              className="mt-4 px-4 py-3.5 rounded-r-lg rounded-bl-lg"
              style={{
                background: 'rgba(185,163,255,0.06)',
                border: '1px solid rgba(185,163,255,0.20)',
                borderLeft: '3px solid #b9a3ff',
              }}
            >
              <div className="font-serif italic text-sm leading-relaxed" style={{ color: '#f4ead6' }}>
                «Чаще всего ты пишешь Мире вечером — между 21 и 23, особенно по средам. По выходным — почти не пишешь.»
              </div>
              <div className="text-[10.5px] mt-1.5 tracking-widest font-mono" style={{ color: 'rgba(185,163,255,0.70)' }}>
                наблюдение Миры
              </div>
            </div>
          </div>
        </div>

        {/* Two columns: personal + personality */}
        <div className="grid grid-cols-[1.2fr_1fr] gap-10">
          {/* Personal data */}
          <div>
            <div className="uppercase text-[10px] font-semibold tracking-[0.18em] text-gold mb-3 flex items-center gap-2">
              <Spark size={10} color="#f5bc7a" /> Личные данные
            </div>
            {editing ? (
              <div className="space-y-3">
                <div>
                  <label className="text-[10px] uppercase tracking-[0.18em] text-text-muted font-semibold">Имя</label>
                  <input value={addressing} onChange={(e) => setAddressing(e.target.value)}
                    className="w-full mt-1 bg-bg-base border border-border-subtle rounded-button px-3 py-2 text-sm text-text-primary placeholder:text-text-faint outline-none" />
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-[0.18em] text-text-muted font-semibold">Как обращаться</label>
                  <div className="flex gap-2 mt-1">
                    {['ты', 'вы'].map((f) => (
                      <button key={f} onClick={() => setAddressForm(addressForm === f ? '' : f)}
                        className={`flex-1 py-2 rounded-button border text-sm transition-colors ${addressForm === f ? 'bg-gold/10 border-border-strong text-gold font-medium' : 'border-border-subtle text-text-secondary hover:text-text-primary'}`}>
                        на «{f}»
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-[0.18em] text-text-muted font-semibold">Откуда</label>
                  <input value={origin} onChange={(e) => setOrigin(e.target.value)} placeholder="Город / страна"
                    className="w-full mt-1 bg-bg-base border border-border-subtle rounded-button px-3 py-2 text-sm text-text-primary placeholder:text-text-faint outline-none" />
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-[0.18em] text-text-muted font-semibold">Чем занимаешься</label>
                  <input value={occupation} onChange={(e) => setOccupation(e.target.value)} placeholder="Род занятий"
                    className="w-full mt-1 bg-bg-base border border-border-subtle rounded-button px-3 py-2 text-sm text-text-primary placeholder:text-text-faint outline-none" />
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-[0.18em] text-text-muted font-semibold">Часовой пояс</label>
                  <select value={timezone} onChange={(e) => setTimezone(e.target.value)}
                    className="w-full mt-1 bg-bg-base border border-border-subtle rounded-button px-3 py-2 text-sm text-text-primary outline-none">
                    <option value="">— не задан —</option>
                    {TIMEZONES.map((tz) => (
                      <option key={tz.value} value={tz.value}>{tz.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="text-[10px] uppercase tracking-[0.18em] text-text-muted font-semibold">Заметки</label>
                  <textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Что ещё рассказать..."
                    className="w-full mt-1 bg-bg-base border border-border-subtle rounded-button px-3 py-2 text-sm text-text-primary placeholder:text-text-faint outline-none resize-none min-h-[64px]" />
                </div>
              </div>
            ) : (
              <div>
                <FormRow label="Имя" value={addressing || profile?.name || '—'} />
                <FormRow label="Как обращаться" value={`${addressing || profile?.name || '—'} · на «${addressForm || 'ты'}»`} hint="Мира использует эту форму в каждом сообщении" />
                <FormRow label="Часовой пояс" value={profile?.timezone || '—'} monoValue />
                <FormRow label="Язык" value="Русский" />
                <FormRow label="Telegram" value={profile?.telegram || '—'} monoValue hint="идентификатор для подключённого бота" />
                <FormRow label="ID пользователя" value={profile?.id || '—'} monoValue hint="нужен при обращении в поддержку" />
              </div>
            )}
          </div>

          {/* Personality + preferences */}
          <div>
            <div className="uppercase text-[10px] font-semibold tracking-[0.18em] text-mystic mb-3 flex items-center gap-2">
              <Spark size={10} color="#b9a3ff" /> Личность Миры
            </div>
            <div
              className="p-4 rounded-xl mb-3.5"
              style={{
                background: 'rgba(185,163,255,0.04)',
                border: '1px solid rgba(185,163,255,0.20)',
              }}
            >
              <div className="text-[11.5px] text-text-muted leading-relaxed mb-3">
                как ты хочешь, чтобы Мира с тобой общалась
              </div>
              <div className="flex flex-wrap gap-1.5 mb-3.5">
                {mannerOptions.map((m) => {
                  const on = manner.includes(m);
                  return (
                    <button
                      key={m}
                      onClick={() => editing && toggleManner(m)}
                      className={`px-3 py-1.5 rounded-pill border text-sm transition-colors ${on ? 'text-mystic font-medium' : 'border-border-subtle text-text-secondary hover:text-text-primary'}`}
                      style={on ? { backgroundColor: 'rgba(185,163,255,0.16)', borderColor: 'rgba(185,163,255,0.50)' } : undefined}
                    >
                      {on && <span className="text-[9px] mr-1">✦</span>}{m}
                    </button>
                  );
                })}
              </div>
              <button className="text-xs tracking-wide" style={{ color: '#b9a3ff', borderBottom: '1px dashed rgba(185,163,255,0.20)', paddingBottom: 1 }}>
                настроить детально →
              </button>
            </div>

            <div className="uppercase text-[10px] font-semibold tracking-[0.18em] text-text-muted mb-3 mt-6">
              предпочтения
            </div>
            <PrefRow
              icon={<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M4 11 V8 A4 4 0 0 1 12 8 V11 L13 12 H3 Z M7 13.5 A1 1 0 0 0 9 13.5" stroke="currentColor" strokeWidth="1.1" strokeLinejoin="round" strokeLinecap="round"/></svg>}
              label="Уведомления"
              value="включены · только важное"
            />
            <PrefRow
              icon={<svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M11.5 8.5 A5 5 0 1 1 5.5 2.5 A4 4 0 0 0 11.5 8.5 Z" stroke="currentColor" strokeWidth="1.1" strokeLinejoin="round"/></svg>}
              label="Тихое время"
              value="00:00 – 07:30"
              mono
            />
            <PrefRow
              icon={<Cloud size={14} />}
              label="Google Drive"
              value={profile?.gdrive_linked ? `подключено · ${profile.gdrive_email || ''}` : 'не подключено'}
              status={profile?.gdrive_linked ? 'ok' : undefined}
            />
            <PrefRow
              icon={<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="3" stroke="currentColor" strokeWidth="1.1"/><circle cx="8" cy="8" r="6" stroke="currentColor" strokeWidth="0.9" strokeOpacity="0.55"/><circle cx="8" cy="2" r="0.8" fill="currentColor"/><circle cx="14" cy="8" r="0.8" fill="currentColor"/><circle cx="8" cy="14" r="0.8" fill="currentColor"/><circle cx="2" cy="8" r="0.8" fill="currentColor"/></svg>}
              label="Память"
              value="хранится локально на сервере"
            />

            <div
              className="mt-5 p-3.5 rounded-[10px]"
              style={{ border: '1px dashed rgba(244,234,214,0.10)' }}
            >
              <div className="uppercase text-[10px] font-semibold tracking-[0.18em] text-rose mb-1.5">
                опасная зона
              </div>
              <div className="text-[11.5px] text-text-muted leading-relaxed mb-2.5">
                забыть меня — Мира удалит все факты, диалоги и связи. отменить нельзя.
              </div>
              {forgotten ? (
                <div className="text-xs text-text-muted" style={{ letterSpacing: '0.04em' }}>
                  ✓ профиль и история сброшены
                </div>
              ) : !confirmForget ? (
                <button
                  onClick={() => setConfirmForget(true)}
                  className="text-xs px-3 py-1.5 rounded-md transition-colors hover:bg-rose/10"
                  style={{
                    color: '#e88a8a',
                    border: '1px solid #e88a8a',
                    background: 'transparent',
                    letterSpacing: '0.04em',
                  }}
                >
                  забыть меня
                </button>
              ) : (
                <div className="flex items-center gap-2">
                  <span className="text-[11px] text-rose font-medium">точно? это необратимо</span>
                  <button
                    onClick={forget}
                    className="text-xs px-3 py-1.5 rounded-md transition-colors"
                    style={{ color: '#070c1c', background: '#e88a8a', letterSpacing: '0.04em' }}
                  >
                    да, забыть
                  </button>
                  <button
                    onClick={() => setConfirmForget(false)}
                    className="text-xs px-3 py-1.5 rounded-md transition-colors hover:bg-white/[0.04]"
                    style={{ color: '#f4ead6', border: '1px solid rgba(244,234,214,0.10)' }}
                  >
                    отмена
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </ScreenShell>
  );
}
