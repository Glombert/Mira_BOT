'use client';

import { useState, useEffect } from 'react';
import { X, Bell, List, Plus, Trash2, Loader2 } from 'lucide-react';
import { ModalShell } from './modal-shell';
import { MiraClient } from '@mira/shared';

interface RemindersModalProps {
  open: boolean;
  onClose: () => void;
  client: MiraClient | null;
}

export function RemindersModal({ open, onClose, client }: RemindersModalProps) {
  const [datetime, setDatetime] = useState('');
  const [text, setText] = useState('');
  const [cancelId, setCancelId] = useState('');
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (open) {
      setDatetime('');
      setText('');
      setCancelId('');
      setResult(null);
      setLoading(false);
    }
  }, [open]);

  const run = async (cmd: string) => {
    if (!client) return;
    setLoading(true);
    setResult(null);
    try {
      const msg = await client.sendCommandAwait(cmd, ['system'], 15000);
      setResult(msg.content);
    } catch {
      setResult('Ошибка: нет ответа от сервера');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = () => {
    if (datetime && text) {
      // Append :00 seconds for server compatibility
      const dt = datetime.includes('T') && datetime.split('T')[1]?.length === 5
        ? `${datetime}:00`
        : datetime;
      run(`remind ${dt} ${text}`);
    }
  };

  return (
    <ModalShell open={open} onClose={onClose}>
      <div className="p-6 max-h-[85vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-text-primary flex items-center gap-2">
            <Bell size={20} className="text-accent" />
            Напоминания
          </h2>
          <button onClick={onClose} aria-label="Закрыть" className="h-8 w-8 flex items-center justify-center rounded-button text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-4">
          <div className="bg-bg-elevated rounded-card p-3 space-y-2">
            <h3 className="text-sm font-medium text-text-primary">Создать</h3>
            <div>
              <label className="block text-xs text-text-secondary mb-1">Когда</label>
              <input
                type="datetime-local"
                value={datetime}
                onChange={(e) => setDatetime(e.target.value)}
                className="w-full bg-bg-input border border-border-default rounded-input px-3 py-2 text-sm text-text-primary outline-none focus:border-border-focus focus:shadow-glow"
              />
            </div>
            <div>
              <label className="block text-xs text-text-secondary mb-1">Текст</label>
              <textarea
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Утренний кофе"
                rows={2}
                className="w-full bg-bg-input border border-border-default rounded-input px-3 py-2 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-border-focus focus:shadow-glow resize-none"
              />
            </div>
            <button
              onClick={handleCreate}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-button bg-accent text-text-on-accent hover:bg-accent-hover shadow-glow transition-colors text-sm"
            >
              <Plus size={16} />
              Создать
            </button>
          </div>

          <div className="bg-bg-elevated rounded-card p-3 space-y-2">
            <h3 className="text-sm font-medium text-text-primary">Действия</h3>
            <button
              onClick={() => run('reminders')}
              className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-button bg-bg-input text-text-primary hover:bg-bg-overlay transition-colors text-sm border border-border-default"
            >
              <List size={16} />
              Показать список
            </button>
            <div className="flex items-center gap-2">
              <input
                value={cancelId}
                onChange={(e) => setCancelId(e.target.value)}
                placeholder="ID напоминания"
                className="flex-1 bg-bg-input border border-border-default rounded-input px-3 py-2 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-border-focus focus:shadow-glow"
              />
              <button
                onClick={() => {
                  if (cancelId) run(`remind_cancel ${cancelId}`);
                }}
                className="px-3 py-2 rounded-button bg-error/10 text-error hover:bg-error/20 transition-colors text-sm"
              >
                <Trash2 size={16} />
              </button>
            </div>
          </div>

          {loading && (
            <div className="flex items-center justify-center gap-2 py-2">
              <Loader2 size={16} className="animate-spin text-accent" />
              <span className="text-sm text-text-secondary">Жду ответа...</span>
            </div>
          )}

          {result && (
            <div className="bg-bg-input rounded-card p-3 border border-border-default">
              <pre className="text-sm text-text-primary whitespace-pre-wrap font-sans">{result}</pre>
            </div>
          )}
        </div>
      </div>
    </ModalShell>
  );
}
