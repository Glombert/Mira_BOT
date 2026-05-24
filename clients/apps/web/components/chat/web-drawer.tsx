'use client';

import { useState, useCallback, useMemo } from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface DrawerCommand {
  cmd: string;
  label: string;
  icon: string;
  category: string;
  requires?: 'gdrive_authorized' | 'owner';
  hasArgs?: boolean;
}

const COMMANDS: DrawerCommand[] = [
  { cmd: 'clear', label: 'Очистить историю', icon: '🗑', category: 'ЧАТ' },
  { cmd: 'whoami', label: 'Профиль', icon: '👤', category: 'ЧАТ' },
  { cmd: 'tz', label: 'Часовой пояс', icon: '🌍', category: 'ЧАТ', hasArgs: true },
  { cmd: 'forget', label: 'Забыть меня', icon: '🔁', category: 'ЧАТ' },
  { cmd: 'stop', label: 'Остановить Конклав', icon: '⏹', category: 'ЧАТ' },
  { cmd: 'files', label: 'Мои файлы', icon: '📂', category: 'ФАЙЛЫ' },
  { cmd: 'gdrive_login', label: 'Привязать Drive', icon: '🔗', category: 'GOOGLE' },
  { cmd: 'gdrive_status', label: 'Drive: статус', icon: '☁️', category: 'GOOGLE' },
  { cmd: 'gdrive_list', label: 'Файлы на Drive', icon: '📋', category: 'GOOGLE', requires: 'gdrive_authorized' },
  { cmd: 'gdrive_get', label: 'Скачать с Drive', icon: '⤓', category: 'GOOGLE', requires: 'gdrive_authorized', hasArgs: true },
  { cmd: 'gdrive_logout', label: 'Отвязать Drive', icon: '✂️', category: 'GOOGLE', requires: 'gdrive_authorized' },
  { cmd: 'gcal', label: 'Календарь', icon: '📅', category: 'GOOGLE', requires: 'gdrive_authorized' },
  { cmd: 'gcal_create', label: 'Создать событие', icon: '➕', category: 'GOOGLE', requires: 'gdrive_authorized', hasArgs: true },
  { cmd: 'gsheet', label: 'Прочитать Таблицу', icon: '📊', category: 'GOOGLE', requires: 'gdrive_authorized', hasArgs: true },
  { cmd: 'gsheet_create', label: 'Создать Таблицу', icon: '📝', category: 'GOOGLE', requires: 'gdrive_authorized', hasArgs: true },
  { cmd: 'remind', label: 'Создать', icon: '➕', category: 'НАПОМИНАНИЯ', hasArgs: true },
  { cmd: 'reminders', label: 'Список', icon: '📋', category: 'НАПОМИНАНИЯ' },
  { cmd: 'task', label: 'Отложить задачу', icon: '➕', category: 'ЗАДАЧИ', hasArgs: true },
  { cmd: 'tasks', label: 'Список задач', icon: '📋', category: 'ЗАДАЧИ' },
  { cmd: 'image', label: 'Сгенерировать картинку', icon: '🖼', category: 'ИНСТРУМЕНТЫ', hasArgs: true },
  { cmd: 'stats', label: 'Метрики LLM', icon: '📊', category: 'ВЛАДЕЛЕЦ', requires: 'owner' },
  { cmd: 'users', label: 'Пользователи', icon: '👥', category: 'ВЛАДЕЛЕЦ', requires: 'owner' },
  { cmd: 'versions', label: 'Резервные копии', icon: '📦', category: 'ВЛАДЕЛЕЦ', requires: 'owner' },
  { cmd: 'blacklist', label: 'Чёрный список', icon: '🚫', category: 'ВЛАДЕЛЕЦ', requires: 'owner' },
  { cmd: 'rename', label: 'Переименовать пользователя', icon: '✏️', category: 'ВЛАДЕЛЕЦ', requires: 'owner', hasArgs: true },
  { cmd: 'help', label: 'Помощь', icon: '❓', category: 'ЧАТ' },
];

interface UserPermissions {
  is_owner: boolean;
  is_approved: boolean;
  gdrive_authorized: boolean;
}

interface WebDrawerProps {
  open: boolean;
  onClose: () => void;
  onRun: (cmd: string) => void;
  permissions: UserPermissions;
  userName: string;
}

export function WebDrawer({ open, onClose, onRun, permissions, userName }: WebDrawerProps) {
  const [formCmd, setFormCmd] = useState<string | null>(null);
  const [formValue, setFormValue] = useState('');

  const grouped = useMemo(() => {
    const cats = Array.from(new Set(COMMANDS.map((c) => c.category)));
    return cats.map((cat) => ({
      cat,
      commands: COMMANDS.filter((c) => c.category === cat),
    }));
  }, []);

  const isDisabled = useCallback(
    (cmd: DrawerCommand) => {
      if (cmd.requires === 'owner' && !permissions.is_owner) return true;
      if (cmd.requires === 'gdrive_authorized' && !permissions.gdrive_authorized) return true;
      return false;
    },
    [permissions]
  );

  const handleClick = (cmd: DrawerCommand) => {
    if (isDisabled(cmd)) return;
    if (cmd.hasArgs) {
      setFormCmd(cmd.cmd);
      setFormValue('');
      return;
    }
    onRun(cmd.cmd);
  };

  const handleFormSubmit = () => {
    if (formCmd && formValue.trim()) {
      onRun(`${formCmd} ${formValue.trim()}`);
      setFormCmd(null);
      setFormValue('');
    }
  };

  return (
    <>
      {/* Mobile overlay */}
      <div
        className={cn(
          'fixed inset-0 z-40 bg-black/40 transition-opacity lg:hidden',
          open ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
        )}
        onClick={onClose}
      />

      {/* Drawer / Sidebar */}
      <aside
        className={cn(
          'fixed lg:sticky lg:top-0 lg:h-[100dvh] z-50 lg:z-auto bg-bg-card border-r border-border-default',
          'w-[280px] transition-transform duration-250',
          open ? 'translate-x-0' : '-translate-x-full lg:translate-x-0 lg:w-0 lg:border-0 lg:overflow-hidden'
        )}
      >
        <div className="flex flex-col h-full p-4 overflow-y-auto">
          <div className="flex items-center justify-between mb-4 lg:hidden">
            <span className="text-text-primary font-semibold">Меню</span>
            <button onClick={onClose} className="text-text-secondary hover:text-text-primary">
              <X size={20} />
            </button>
          </div>

          <div className="mb-4 pb-3 border-b border-border-subtle">
            <div className="text-text-primary font-medium">{userName || 'Гость'}</div>
            <div className="text-xs text-text-secondary">
              {permissions.is_owner ? 'Владелец' : permissions.is_approved ? 'Одобрен' : 'Гость'}
            </div>
          </div>

          {grouped.map((section) => {
            if (section.cat === 'ВЛАДЕЛЕЦ' && !permissions.is_owner) return null;
            return (
              <div key={section.cat} className="mb-3">
                <div className="text-[10px] uppercase tracking-wider text-text-muted font-bold mb-1">
                  {section.cat}
                </div>
                {section.commands.map((cmd) => {
                  const disabled = isDisabled(cmd);
                  return (
                    <button
                      key={cmd.cmd}
                      onClick={() => handleClick(cmd)}
                      disabled={disabled}
                      className={cn(
                        'w-full text-left px-2 py-1.5 rounded-button text-sm flex items-center gap-2',
                        disabled
                          ? 'text-text-muted cursor-not-allowed opacity-50'
                          : 'text-text-primary hover:bg-bg-elevated'
                      )}
                    >
                      <span>{cmd.icon}</span>
                      <span>{cmd.label}</span>
                      {cmd.hasArgs && !disabled && <span className="ml-auto text-text-muted text-xs">⋯</span>}
                    </button>
                  );
                })}
              </div>
            );
          })}
        </div>
      </aside>

      {/* Inline form modal for args */}
      {formCmd && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50">
          <div className="bg-bg-card border border-border-default rounded-card p-6 w-full max-w-sm">
            <h3 className="text-text-primary font-semibold mb-3">{formCmd}</h3>
            <textarea
              value={formValue}
              onChange={(e) => setFormValue(e.target.value)}
              className="w-full bg-bg-input border border-border-default rounded-input p-3 text-text-primary placeholder:text-text-muted resize-none outline-none min-h-[80px] mb-4"
              placeholder="Введите параметры..."
              autoFocus
            />
            <div className="flex gap-2 justify-end">
              <button onClick={() => setFormCmd(null)} className="px-4 py-2 rounded-button text-text-secondary hover:bg-bg-elevated">
                Отмена
              </button>
              <button onClick={handleFormSubmit} className="px-4 py-2 rounded-button bg-accent text-text-on-accent hover:bg-accent-hover">
                Отправить
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
