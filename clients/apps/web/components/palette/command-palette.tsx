'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { Search, X } from 'lucide-react';
import { COMMANDS, type CommandDef } from '@/lib/commands';
import { ModalShell } from '@/components/ui/modal-shell';

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  onRun: (cmd: string) => void;
}

export function CommandPalette({ open, onClose, onRun }: CommandPaletteProps) {
  const [query, setQuery] = useState('');
  const [selected, setSelected] = useState<CommandDef | null>(null);
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery('');
      setSelected(null);
      setFormValues({});
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  const filtered = COMMANDS.filter(
    (c) =>
      c.label.toLowerCase().includes(query.toLowerCase()) ||
      c.description.toLowerCase().includes(query.toLowerCase()) ||
      c.cmd.toLowerCase().includes(query.toLowerCase())
  );

  const handleSelect = useCallback((cmd: CommandDef) => {
    if (cmd.destructive) {
      if (!window.confirm(`Точно «${cmd.label}»? Действие необратимо.`)) return;
    }
    if (cmd.hasArgs && cmd.args) {
      setSelected(cmd);
      const defaults: Record<string, string> = {};
      cmd.args.forEach((a) => {
        if (a.type === 'datetime-local') defaults[a.name] = '';
        else if (a.type === 'number') defaults[a.name] = '10';
        else defaults[a.name] = '';
      });
      setFormValues(defaults);
    } else {
      onRun(cmd.cmd);
      onClose();
    }
  }, [onRun, onClose]);

  const handleFormSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault();
    if (!selected) return;
    const parts = [selected.cmd];
    selected.args?.forEach((a) => {
      const val = formValues[a.name]?.trim();
      if (val) parts.push(val);
    });
    onRun(parts.join(' '));
    onClose();
  }, [selected, formValues, onRun, onClose]);

  return (
    <ModalShell open={open} onClose={onClose}>
      {!selected ? (
        <>
          <div className="flex items-center gap-3 px-4 py-3 border-b border-border-subtle">
            <Search size={18} className="text-text-muted shrink-0" />
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Команда..."
              className="flex-1 bg-transparent text-text-primary placeholder:text-text-muted outline-none text-base"
            />
            <kbd className="hidden sm:inline-block text-xs text-text-muted bg-bg-elevated px-1.5 py-0.5 rounded border border-border-subtle">Esc</kbd>
          </div>
          <div className="max-h-[50vh] overflow-y-auto py-2">
            {filtered.length === 0 && (
              <p className="px-4 py-6 text-sm text-text-muted text-center">Ничего не найдено</p>
            )}
            {filtered.map((cmd) => {
              const Icon = cmd.icon;
              return (
                <button
                  key={cmd.id}
                  onClick={() => handleSelect(cmd)}
                  className="w-full flex items-center gap-3 px-4 py-2.5 text-left hover:bg-bg-elevated transition-colors"
                >
                  <Icon size={18} className="text-text-secondary shrink-0" />
                  <div className="min-w-0">
                    <p className="text-sm text-text-primary">{cmd.label}</p>
                    <p className="text-xs text-text-secondary">{cmd.description}</p>
                  </div>
                </button>
              );
            })}
          </div>
        </>
      ) : (
        <form onSubmit={handleFormSubmit} className="p-4 space-y-3">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-base font-medium text-text-primary">{selected.label}</h3>
            <button
              type="button"
              onClick={() => setSelected(null)}
              className="h-8 w-8 flex items-center justify-center rounded-button text-text-secondary hover:text-text-primary hover:bg-bg-elevated"
              aria-label="Назад"
            >
              <X size={16} />
            </button>
          </div>
          {selected.args?.map((arg) => (
            <div key={arg.name}>
              <label className="block text-xs text-text-secondary mb-1">{arg.label}{!arg.optional && ' *'}</label>
              {arg.type === 'textarea' ? (
                <textarea
                  value={formValues[arg.name] || ''}
                  onChange={(e) => setFormValues((v) => ({ ...v, [arg.name]: e.target.value }))}
                  placeholder={arg.placeholder}
                  rows={3}
                  className="w-full bg-bg-input border border-border-default rounded-input px-3 py-2 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-border-focus focus:shadow-glow transition-all"
                />
              ) : (
                <input
                  type={arg.type}
                  value={formValues[arg.name] || ''}
                  onChange={(e) => setFormValues((v) => ({ ...v, [arg.name]: e.target.value }))}
                  placeholder={arg.placeholder}
                  className="w-full bg-bg-input border border-border-default rounded-input px-3 py-2 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-border-focus focus:shadow-glow transition-all"
                />
              )}
            </div>
          ))}
          <div className="flex justify-end gap-2 pt-1">
            <button
              type="button"
              onClick={() => setSelected(null)}
              className="px-4 py-2 rounded-button text-sm text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors"
            >
              Назад
            </button>
            <button
              type="submit"
              className="px-4 py-2 rounded-button text-sm bg-accent text-text-on-accent hover:bg-accent-hover shadow-glow transition-colors"
            >
              Отправить
            </button>
          </div>
        </form>
      )}
    </ModalShell>
  );
}
