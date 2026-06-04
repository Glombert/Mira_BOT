'use client';

import React, { useState } from 'react';
import { X } from 'lucide-react';
import { ModalShell } from './modal-shell';
import { TzPicker } from './tz-picker';
import type { MiraClient } from '@mira/shared';

interface Props {
  open: boolean;
  onClose: () => void;
  client: MiraClient | null;
}

export function CreateReminderModal({ open, onClose, client }: Props) {
  const [title, setTitle] = useState('');
  const [at, setAt] = useState('');
  const [timezone, setTimezone] = useState('Europe/Moscow');
  const [repeat, setRepeat] = useState('');
  const [saving, setSaving] = useState(false);

  if (!open) return null;

  const handleSubmit = () => {
    if (!client || !title.trim() || !at.trim()) return;
    setSaving(true);
    const cmd = `remind ${at.trim()} ${title.trim()}${repeat ? ` repeat ${repeat}` : ''}`;
    client.sendCommand(cmd);
    setTimeout(() => {
      setSaving(false);
      setTitle('');
      setAt('');
      setRepeat('');
      onClose();
    }, 400);
  };

  return (
    <ModalShell open={open} onClose={onClose}>
      <div className="p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-serif italic text-gold">Новое напоминание</h2>
          <button onClick={onClose} aria-label="Закрыть"
            className="h-8 w-8 flex items-center justify-center rounded-button text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="text-[10px] uppercase tracking-[0.18em] text-text-muted font-semibold block mb-1.5">Что напомнить</label>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Например, позвонить Кате"
              className="w-full bg-bg-base border border-border-subtle rounded-button px-3 py-2 text-sm text-text-primary placeholder:text-text-faint outline-none"
            />
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-[0.18em] text-text-muted font-semibold block mb-1.5">Когда</label>
            <input
              value={at}
              onChange={(e) => setAt(e.target.value)}
              placeholder="завтра в 9:00 или 2026-06-05 09:00"
              className="w-full bg-bg-base border border-border-subtle rounded-button px-3 py-2 text-sm text-text-primary placeholder:text-text-faint outline-none"
            />
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-[0.18em] text-text-muted font-semibold block mb-1.5">Часовой пояс</label>
            <TzPicker value={timezone} onChange={setTimezone} />
          </div>

          <div>
            <label className="text-[10px] uppercase tracking-[0.18em] text-text-muted font-semibold block mb-1.5">Повтор</label>
            <div className="flex gap-2 flex-wrap">
              {['каждый день', 'по будням', 'каждую неделю', 'каждый месяц'].map((r) => (
                <button
                  key={r}
                  onClick={() => setRepeat(repeat === r ? '' : r)}
                  className={`px-3 py-1.5 rounded-pill border text-xs transition-colors ${repeat === r ? 'bg-gold/10 border-border-strong text-gold' : 'border-border-subtle text-text-secondary hover:text-text-primary'}`}
                >
                  {r}
                </button>
              ))}
            </div>
          </div>

          <button
            onClick={handleSubmit}
            disabled={!title.trim() || !at.trim() || saving}
            className="w-full py-2.5 rounded-button bg-gold text-bg-base font-medium disabled:opacity-60 transition-opacity"
          >
            {saving ? 'Создание…' : 'Создать напоминание'}
          </button>
        </div>
      </div>
    </ModalShell>
  );
}
