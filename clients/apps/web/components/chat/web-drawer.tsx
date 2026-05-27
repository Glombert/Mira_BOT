'use client';

import { useState, useCallback, useMemo } from 'react';
import { X, Search, Command } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { UserEntry } from '@mira/shared';

// Справочные команды → результат панелью в меню (не в чат)
const INFO_CMDS = new Set([
  'whoami', 'help', 'stats', 'versions', 'rituals', 'blacklist',
  'evolution_count', 'gdrive_status', 'gcal', 'reminders', 'tasks',
]);
const STATUS_LABEL: Record<string, string> = {
  owner: 'Владелец', regular: 'Одобрен', guest: 'Гость',
  rejected: 'Отклонён', blacklisted: 'Чёрный список', blocked: 'Блок',
};

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
  { cmd: 'gdrive_toggle', label: 'Auto-upload', icon: '⚡', category: 'GOOGLE', requires: 'gdrive_authorized' },
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
  { cmd: 'evolution_count', label: 'Счётчик /evolve', icon: '🧬', category: 'ВЛАДЕЛЕЦ', requires: 'owner' },
  { cmd: 'rituals', label: 'Ритуалы', icon: '🤖', category: 'ВЛАДЕЛЕЦ', requires: 'owner' },
  { cmd: 'reflect', label: 'Само-ревью', icon: '🔍', category: 'ВЛАДЕЛЕЦ', requires: 'owner' },
  { cmd: 'kidmode', label: 'Детский режим', icon: '👶', category: 'ВЛАДЕЛЕЦ', requires: 'owner', hasArgs: true },
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
  onFetchInfo?: (cmd: string) => Promise<string>;
  onFetchUsers?: () => Promise<UserEntry[]>;
}

export function WebDrawer({ open, onClose, onRun, permissions, userName, onFetchInfo, onFetchUsers }: WebDrawerProps) {
  const [formCmd, setFormCmd] = useState<string | null>(null);
  const [formValue, setFormValue] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  // info-панели
  const [infoOpen, setInfoOpen] = useState<string | null>(null);
  const [infoText, setInfoText] = useState<Record<string, string>>({});
  const [infoLoading, setInfoLoading] = useState<string | null>(null);
  const toggleInfo = useCallback((cmd: string) => {
    setInfoOpen((prev) => {
      if (prev === cmd) return null;
      if (onFetchInfo && infoText[cmd] === undefined) {
        setInfoLoading(cmd);
        onFetchInfo(cmd)
          .then((t) => setInfoText((m) => ({ ...m, [cmd]: t })))
          .catch(() => setInfoText((m) => ({ ...m, [cmd]: 'Не удалось получить данные' })))
          .finally(() => setInfoLoading(null));
      }
      return cmd;
    });
  }, [onFetchInfo, infoText]);

  // список пользователей
  const [usersExpanded, setUsersExpanded] = useState(false);
  const [usersList, setUsersList] = useState<UserEntry[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [openUserId, setOpenUserId] = useState<string | null>(null);
  const loadUsers = useCallback(() => {
    if (!onFetchUsers) return;
    setUsersLoading(true);
    onFetchUsers().then(setUsersList).catch(() => {}).finally(() => setUsersLoading(false));
  }, [onFetchUsers]);
  const toggleUsers = useCallback(() => {
    setUsersExpanded((prev) => {
      const next = !prev;
      if (next && usersList.length === 0) loadUsers();
      return next;
    });
  }, [usersList.length, loadUsers]);
  const userAction = useCallback((cmd: string) => {
    onRun(cmd);
    setOpenUserId(null);
    setTimeout(loadUsers, 600);
  }, [onRun, loadUsers]);

  const grouped = useMemo(() => {
    const cats = Array.from(new Set(COMMANDS.map((c) => c.category)));
    return cats.map((cat) => ({
      cat,
      commands: COMMANDS.filter((c) => c.category === cat),
    }));
  }, []);

  const filteredGrouped = useMemo(() => {
    if (!searchQuery.trim()) return grouped;
    const q = searchQuery.toLowerCase();
    return grouped
      .map((section) => ({
        ...section,
        commands: section.commands.filter(
          (cmd) =>
            cmd.label.toLowerCase().includes(q) ||
            cmd.cmd.toLowerCase().includes(q)
        ),
      }))
      .filter((section) => section.commands.length > 0);
  }, [grouped, searchQuery]);

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
          'fixed inset-0 z-40 bg-black/55 transition-opacity',
          open ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
        )}
        onClick={onClose}
      />

      {/* Drawer / Sidebar */}
      <aside
        className={cn(
          'fixed top-0 left-0 h-[100dvh] z-50 bg-bg-sidebar border-r border-border-subtle shadow-drawer',
          'w-[280px] transition-transform duration-250',
          open ? 'translate-x-0' : '-translate-x-full'
        )}
      >
        <div className="flex flex-col h-full overflow-y-auto">
          {/* Header */}
          <div className="flex items-center gap-3 p-4 border-b border-border-divider">
            <div className="relative">
              <img
                src="/mira-avatar-full.png"
                alt="Мира"
                className="w-11 h-11 rounded-full object-cover border border-gold-soft"
              />
              <span className="absolute bottom-0.5 right-0.5 w-2.5 h-2.5 rounded-full bg-gold border-2 border-bg-sidebar" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-serif text-[19px] text-text-primary truncate">{userName || 'Гость'}</div>
              <div className="text-[11px] text-text-secondary tracking-wide">
                {permissions.is_owner ? 'Владелец' : permissions.is_approved ? 'Одобрен' : 'Гость'}
              </div>
            </div>
            <button
              onClick={onClose}
              className="text-text-muted hover:text-text-primary p-1"
              aria-label="Закрыть"
            >
              <X size={18} />
            </button>
          </div>

          {/* Search */}
          <div className="px-4 pt-4 pb-2">
            <div className="flex items-center gap-2 px-3 py-2 bg-bg-elevated border border-border-subtle rounded-input-mobile">
              <Search size={15} className="text-text-faint shrink-0" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Поиск команд..."
                className="flex-1 bg-transparent text-text-primary text-[13px] placeholder:text-text-faint outline-none"
              />
              {searchQuery && (
                <button onClick={() => setSearchQuery('')} className="text-text-faint hover:text-text-muted">
                  <X size={14} />
                </button>
              )}
            </div>
          </div>

          {/* Sections */}
          <div className="flex-1 px-4 pb-2">
            {filteredGrouped.map((section) => {
              if (section.cat === 'ВЛАДЕЛЕЦ' && !permissions.is_owner) return null;
              return (
                <div key={section.cat} className="mb-3">
                  <div className="flex items-center gap-1.5 mb-1">
                    <Command size={14} className="text-text-muted" />
                    <div className="text-[10px] uppercase tracking-[0.18em] text-text-muted font-semibold">
                      {section.cat}
                    </div>
                  </div>
                  {section.commands.map((cmd) => {
                    const disabled = isDisabled(cmd);

                    // «Пользователи» — выпадающий список с подменю действий
                    if (cmd.cmd === 'users' && onFetchUsers && permissions.is_owner && !searchQuery) {
                      return (
                        <div key="users">
                          <button onClick={toggleUsers} className="w-full text-left px-2 py-[7px] rounded-sidebar-item text-[13px] flex items-center gap-2 text-text-primary hover:bg-gold/5 hover:text-gold transition-colors">
                            <span className="text-sm">{cmd.icon}</span>
                            <span>{cmd.label}</span>
                            <span className="ml-auto text-text-muted text-xs">{usersExpanded ? '▾' : '▸'}</span>
                          </button>
                          {usersExpanded && (
                            <div className="ml-4 pl-2 border-l border-border-divider">
                              {usersLoading && <div className="text-xs text-text-muted py-1">Загрузка…</div>}
                              {!usersLoading && usersList.length === 0 && <div className="text-xs text-text-muted py-1">Пусто</div>}
                              {usersList.map((u) => (
                                <div key={u.id}>
                                  <button onClick={() => setOpenUserId(openUserId === u.id ? null : u.id)} className="w-full flex items-center justify-between py-2 px-1 text-left">
                                    <span className="text-[13px] text-text-primary truncate mr-2">{u.name || u.id}</span>
                                    <span className="text-[10px] text-gold font-mono shrink-0">{STATUS_LABEL[u.status] || u.status}</span>
                                  </button>
                                  {openUserId === u.id && (
                                    <div className="pl-1 pb-1">
                                      <button onClick={() => { setOpenUserId(null); setFormCmd(`rename ${u.id}`); setFormValue(''); }} className="block w-full text-left py-1.5 px-2 text-[13px] text-text-dim hover:text-gold rounded-sidebar-item">Переименовать</button>
                                      <button onClick={() => userAction(`approve ${u.id}`)} className="block w-full text-left py-1.5 px-2 text-[13px] text-text-dim hover:text-gold rounded-sidebar-item">Одобрить</button>
                                      <button onClick={() => userAction(`reject ${u.id}`)} className="block w-full text-left py-1.5 px-2 text-[13px] text-text-dim hover:text-gold rounded-sidebar-item">Отклонить</button>
                                      <button onClick={() => userAction(`block ${u.id}`)} className="block w-full text-left py-1.5 px-2 text-[13px] text-rose hover:opacity-80 rounded-sidebar-item">Заблокировать</button>
                                    </div>
                                  )}
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      );
                    }

                    // Справочные команды — раскрываются панелью с результатом
                    if (INFO_CMDS.has(cmd.cmd) && onFetchInfo && !disabled && !searchQuery) {
                      const o = infoOpen === cmd.cmd;
                      return (
                        <div key={cmd.cmd}>
                          <button onClick={() => toggleInfo(cmd.cmd)} className="w-full text-left px-2 py-[7px] rounded-sidebar-item text-[13px] flex items-center gap-2 text-text-primary hover:bg-gold/5 hover:text-gold transition-colors">
                            <span className="text-sm">{cmd.icon}</span>
                            <span>{cmd.label}</span>
                            <span className="ml-auto text-text-muted text-xs">{o ? '▾' : '▸'}</span>
                          </button>
                          {o && (
                            <div className="ml-4 pl-2 py-1 border-l border-border-divider">
                              {infoLoading === cmd.cmd
                                ? <div className="text-xs text-text-muted">Загрузка…</div>
                                : <div className="text-xs text-text-secondary font-mono whitespace-pre-wrap leading-relaxed">{infoText[cmd.cmd] || '—'}</div>}
                            </div>
                          )}
                        </div>
                      );
                    }

                    return (
                      <button
                        key={cmd.cmd}
                        onClick={() => handleClick(cmd)}
                        disabled={disabled}
                        className={cn(
                          'w-full text-left px-2 py-[7px] rounded-sidebar-item text-[13px] flex items-center gap-2 transition-colors',
                          disabled
                            ? 'text-text-faint cursor-not-allowed opacity-40'
                            : 'text-text-primary hover:bg-gold/5 hover:text-gold'
                        )}
                      >
                        <span className="text-sm">{cmd.icon}</span>
                        <span>{cmd.label}</span>
                        {cmd.hasArgs && !disabled && <span className="ml-auto text-text-muted text-xs">⋯</span>}
                      </button>
                    );
                  })}
                </div>
              );
            })}
          </div>

          {/* Footer */}
          <div className="px-4 pt-3 pb-4 border-t border-border-divider">
            <div className="text-[11px] text-text-muted font-mono tracking-wide">Версия 0.1.0</div>
            <a
              href="https://github.com/Glombert/Mira_BOT"
              target="_blank"
              rel="noopener noreferrer"
              className="text-[11px] text-gold hover:underline mt-0.5 block"
            >
              github.com/Glombert/Mira_BOT
            </a>
          </div>
        </div>
      </aside>

      {/* Inline form modal for args */}
      {formCmd && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50">
          <div className="bg-bg-elevated border border-border-subtle rounded-card p-6 w-full max-w-sm shadow-elevated">
            <h3 className="text-gold font-serif text-lg font-medium mb-3">{formCmd}</h3>
            <textarea
              value={formValue}
              onChange={(e) => setFormValue(e.target.value)}
              className="w-full bg-bg-deep border border-border-subtle rounded-input p-3 text-text-primary placeholder:text-text-faint resize-none outline-none min-h-[80px] mb-4 font-serif"
              placeholder="Введите параметры..."
              autoFocus
            />
            <div className="flex gap-2 justify-end">
              <button onClick={() => setFormCmd(null)} className="px-4 py-2 rounded-button text-text-secondary hover:bg-gold/5 border border-border-subtle transition-colors">
                Отмена
              </button>
              <button onClick={handleFormSubmit} className="px-4 py-2 rounded-button bg-gold text-bg-base hover:bg-accent-hover transition-colors">
                Отправить
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
