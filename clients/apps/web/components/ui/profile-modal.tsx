'use client';

import { useState, useEffect, useCallback } from 'react';
import { X, Cloud, ChevronDown } from 'lucide-react';
import { ModalShell } from './modal-shell';
import { TIMEZONES, tzLabel } from '@/lib/timezones';
import type { MiraClient, ProfileData } from '@mira/shared';

const WEB_VERSION = '0.1.0';

const ROLE_LABEL: Record<string, string> = {
  owner: 'Владелец', regular: 'Одобрен', guest: 'Гость',
  rejected: 'Отклонён', blacklisted: 'Чёрный список', blocked: 'Заблокирован', kid: 'Детский режим',
};

const MANNER_FALLBACK = ['тёплая', 'вдумчивая', 'немногословная', 'игривая', 'формальная', 'дерзкая', 'заботливая', 'прямая'];

interface Props {
  open: boolean;
  onClose: () => void;
  client: MiraClient | null;
  onboarding?: boolean;
}

export function ProfileModal({ open, onClose, client, onboarding = false }: Props) {
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [tzPickerOpen, setTzPickerOpen] = useState(false);
  const [forgetMode, setForgetMode] = useState(false);
  const [forgetText, setForgetText] = useState('');

  const [addressing, setAddressing] = useState('');
  const [addressForm, setAddressForm] = useState('');
  const [manner, setManner] = useState<string[]>([]);
  const [origin, setOrigin] = useState('');
  const [occupation, setOccupation] = useState('');
  const [notes, setNotes] = useState('');
  const [timezone, setTimezone] = useState('');

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
    if (open) { setTzPickerOpen(false); setForgetMode(false); setForgetText(''); load(); }
  }, [open, load]);

  const toggleManner = (m: string) => setManner((prev) => (prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m]));

  const save = useCallback((skip = false) => {
    if (!client) return;
    setSaving(true);
    client.saveProfile(skip ? {} : {
      addressing: addressing.trim(), address_form: addressForm, manner,
      origin: origin.trim(), occupation: occupation.trim(), notes: notes.trim(), timezone: timezone.trim(),
    });
    setTimeout(() => { setSaving(false); onClose(); }, 250);
  }, [client, addressing, addressForm, manner, origin, occupation, notes, timezone, onClose]);

  const doForget = useCallback(() => {
    if (forgetText.trim().toLowerCase() !== 'забудь') return;
    client?.sendCommand('forget');
    onClose();
  }, [client, forgetText, onClose]);

  if (!open) return null;

  const initial = (addressing || profile?.name || '?').trim().charAt(0).toUpperCase() || '?';
  const roleLabel = profile ? ROLE_LABEL[profile.role] || profile.role : '';
  const mannerOptions = profile?.manner_options?.length ? profile.manner_options : MANNER_FALLBACK;

  return (
    <ModalShell open={open} onClose={onClose}>
      <div className="p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-serif italic text-gold">{onboarding ? 'Расскажи о себе' : 'Профиль'}</h2>
          <button onClick={onClose} aria-label="Закрыть"
            className="h-8 w-8 flex items-center justify-center rounded-button text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors">
            <X size={18} />
          </button>
        </div>

        {loading && !profile ? (
          <div className="py-10 text-center text-text-muted text-sm">Загрузка…</div>
        ) : (
          <div className="space-y-5">
            {onboarding && (
              <p className="text-sm text-text-secondary">Заполни, если хочешь — так Мира станет ближе именно тебе. Всё необязательно.</p>
            )}

            {!onboarding && profile && (
              <>
                <div className="flex flex-col items-center">
                  <div className="w-[72px] h-[72px] rounded-full flex items-center justify-center mb-2 bg-gold/10 border border-border-strong">
                    <span className="font-serif text-3xl text-gold">{initial}</span>
                  </div>
                  <div className="font-serif italic text-2xl text-text-primary truncate max-w-full">{addressing || profile.name || 'Без имени'}</div>
                  <span className="mt-1 px-3 py-0.5 rounded-full bg-gold/10 border border-border-strong text-[11px] tracking-wide text-gold">{roleLabel}</span>
                </div>
                <div>
                  <div className="font-serif italic text-text-secondary mb-2">наша связь</div>
                  <div className="grid grid-cols-2 gap-2">
                    <Stat value={String(profile.days_together)} label="дней" />
                    <Stat value={String(profile.conversations)} label="бесед" />
                    <Stat value={String(profile.memory_facts)} label="фактов" />
                    <Stat value={WEB_VERSION} label="версия" />
                  </div>
                </div>
                {profile.summary ? (
                  <div className="rounded-card p-3" style={{ backgroundColor: 'rgba(185,163,255,0.08)', border: '1px solid rgba(185,163,255,0.24)' }}>
                    <div className="text-[11px] tracking-wide text-mystic mb-1">✦ что Мира знает о тебе</div>
                    <div className="font-serif italic text-sm text-text-primary leading-snug">{profile.summary}</div>
                  </div>
                ) : null}
              </>
            )}

            {/* Анкета */}
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-text-muted font-semibold mb-1.5">✦ Как обращаться</div>
              <input value={addressing} onChange={(e) => setAddressing(e.target.value)} placeholder="Имя или как тебя называть"
                className="w-full bg-bg-base border border-border-subtle rounded-button px-3 py-2 text-sm text-text-primary placeholder:text-text-faint outline-none mb-2" />
              <div className="flex gap-2">
                {['ты', 'вы'].map((f) => (
                  <button key={f} onClick={() => setAddressForm(addressForm === f ? '' : f)}
                    className={`flex-1 py-2 rounded-button border text-sm transition-colors ${addressForm === f ? 'bg-gold/10 border-border-strong text-gold font-medium' : 'border-border-subtle text-text-secondary hover:text-text-primary'}`}>
                    на «{f}»
                  </button>
                ))}
              </div>
            </div>

            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-text-muted font-semibold mb-1">✦ Манера Миры</div>
              <div className="text-[11px] text-text-muted mb-2">Мира останется собой — это лишь тон под тебя</div>
              <div className="flex flex-wrap gap-2">
                {mannerOptions.map((m) => {
                  const on = manner.includes(m);
                  return (
                    <button key={m} onClick={() => toggleManner(m)}
                      className={`px-3 py-1.5 rounded-full border text-sm transition-colors ${on ? 'text-mystic font-medium' : 'border-border-subtle text-text-secondary hover:text-text-primary'}`}
                      style={on ? { backgroundColor: 'rgba(185,163,255,0.16)', borderColor: 'rgba(185,163,255,0.5)' } : undefined}>
                      {m}
                    </button>
                  );
                })}
              </div>
            </div>

            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-text-muted font-semibold mb-1.5">✦ О тебе</div>
              <div className="space-y-2">
                <input value={origin} onChange={(e) => setOrigin(e.target.value)} placeholder="Откуда (город / страна)"
                  className="w-full bg-bg-base border border-border-subtle rounded-button px-3 py-2 text-sm text-text-primary placeholder:text-text-faint outline-none" />
                <input value={occupation} onChange={(e) => setOccupation(e.target.value)} placeholder="Чем занимаешься"
                  className="w-full bg-bg-base border border-border-subtle rounded-button px-3 py-2 text-sm text-text-primary placeholder:text-text-faint outline-none" />
                <div className="relative">
                  <button onClick={() => setTzPickerOpen((v) => !v)}
                    className="w-full flex items-center bg-bg-base border border-border-subtle rounded-button px-3 py-2 text-sm text-left">
                    <span className={timezone ? 'text-text-primary' : 'text-text-faint'}>{timezone ? tzLabel(timezone) : 'Часовой пояс — выбрать из списка'}</span>
                    <ChevronDown size={15} className="ml-auto text-text-muted" />
                  </button>
                  {tzPickerOpen && (
                    <div className="absolute z-10 left-0 right-0 mt-1 max-h-56 overflow-y-auto rounded-card bg-bg-overlay border border-border-subtle shadow-elevated">
                      {TIMEZONES.map((t) => (
                        <button key={t.value} onClick={() => { setTimezone(t.value); setTzPickerOpen(false); }}
                          className={`w-full text-left px-3 py-2 text-sm hover:bg-gold/5 ${timezone === t.value ? 'text-gold' : 'text-text-primary'}`}>
                          {t.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Что ещё рассказать: интересы, привычки, что важно знать…"
                  className="w-full bg-bg-base border border-border-subtle rounded-button px-3 py-2 text-sm text-text-primary placeholder:text-text-faint outline-none resize-none min-h-[64px]" />
              </div>
            </div>

            <div>
              <button onClick={() => save(false)} disabled={saving}
                className="w-full py-2.5 rounded-button bg-gold text-bg-base font-medium disabled:opacity-60">
                {saving ? '…' : 'Сохранить'}
              </button>
              {onboarding && (
                <button onClick={() => save(true)} className="w-full py-2 mt-1 text-sm text-text-secondary hover:text-text-primary">Пропустить</button>
              )}
            </div>

            {!onboarding && profile && (
              <>
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

                <div>
                  <div className="text-[10px] uppercase tracking-[0.18em] text-rose font-semibold mb-1.5">⚠ Опасная зона</div>
                  {!forgetMode ? (
                    <button onClick={() => setForgetMode(true)} className="w-full py-2.5 rounded-button border text-rose font-medium"
                      style={{ borderColor: 'rgba(232,138,138,0.4)', backgroundColor: 'rgba(232,138,138,0.08)' }}>
                      Забыть меня
                    </button>
                  ) : (
                    <div className="rounded-card p-3" style={{ border: '1px solid rgba(232,138,138,0.4)', backgroundColor: 'rgba(232,138,138,0.06)' }}>
                      <div className="text-sm text-text-primary mb-2">Мира удалит профиль, историю и всё, что запомнила. Необратимо. Введите <b className="text-rose">забудь</b>.</div>
                      <div className="flex items-center gap-2">
                        <input value={forgetText} onChange={(e) => setForgetText(e.target.value)} placeholder="забудь" autoFocus
                          className="flex-1 bg-bg-surface border border-border-subtle rounded-button px-3 py-1.5 text-sm text-text-primary placeholder:text-text-faint outline-none" />
                        <button onClick={doForget} disabled={forgetText.trim().toLowerCase() !== 'забудь'}
                          className="px-3 py-1.5 rounded-button text-bg-base text-sm font-medium disabled:opacity-40" style={{ backgroundColor: '#e88a8a' }}>
                          Удалить
                        </button>
                        <button onClick={() => { setForgetMode(false); setForgetText(''); }} className="text-text-muted hover:text-text-primary"><X size={16} /></button>
                      </div>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </ModalShell>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="bg-bg-base border border-border-subtle rounded-card py-3 flex flex-col items-center">
      <span className="text-gold font-mono text-lg truncate max-w-full px-1">{value}</span>
      <span className="text-[10px] text-text-muted mt-0.5 tracking-wide">{label}</span>
    </div>
  );
}
