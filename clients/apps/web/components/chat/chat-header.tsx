'use client';

import { User, Trash2, Bell, Cloud, Menu } from 'lucide-react';
import { StatusDot, type ConnectionStatus } from '@/components/ui/status-dot';

interface ChatHeaderProps {
  userName?: string;
  connectionStatus: ConnectionStatus;
  onClear: () => void;
  onWhoami: () => void;
  onOpenPalette: () => void;
  onOpenReminders: () => void;
  onOpenDrive: () => void;
}

export function ChatHeader({ userName, connectionStatus, onClear, onWhoami, onOpenPalette, onOpenReminders, onOpenDrive }: ChatHeaderProps) {
  return (
    <header className="flex items-center justify-between px-4 py-3 border-b border-border-subtle bg-bg-base sticky top-0 z-10">
      <div className="flex items-center gap-3">
        <button
          onClick={onOpenPalette}
          aria-label="Меню"
          className="h-9 w-9 flex items-center justify-center rounded-button text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors duration-fast"
        >
          <Menu size={20} />
        </button>
        <img src="/mira-avatar-full.png" alt="Мира" className="w-10 h-10 rounded-full object-cover" />
        <div>
          <h1 className="text-xl font-semibold text-text-primary leading-tight">Мира</h1>
          <div className="flex items-center gap-1.5">
            <StatusDot status={connectionStatus} />
            <span className="text-xs text-text-secondary">
              {connectionStatus === 'online' && 'В сети'}
              {connectionStatus === 'reconnecting' && 'Переподключение...'}
              {connectionStatus === 'offline' && 'Не в сети'}
            </span>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-1">
        <span className="text-sm text-text-secondary hidden sm:inline mr-2">{userName}</span>
        <button
          onClick={onOpenReminders}
          aria-label="Напоминания"
          className="h-9 w-9 flex items-center justify-center rounded-button text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors duration-fast"
        >
          <Bell size={20} />
        </button>
        <button
          onClick={onOpenDrive}
          aria-label="Google Drive"
          className="h-9 w-9 flex items-center justify-center rounded-button text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors duration-fast"
        >
          <Cloud size={20} />
        </button>
        <button
          onClick={onWhoami}
          aria-label="Профиль"
          className="h-9 w-9 flex items-center justify-center rounded-button text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors duration-fast"
        >
          <User size={20} />
        </button>
        <button
          onClick={onClear}
          aria-label="Очистить историю"
          className="h-9 w-9 flex items-center justify-center rounded-button text-text-secondary hover:text-error hover:bg-bg-elevated transition-colors duration-fast"
        >
          <Trash2 size={20} />
        </button>
      </div>
    </header>
  );
}
