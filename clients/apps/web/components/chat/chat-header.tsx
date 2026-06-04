'use client';

import { User, Trash2, Bell, Cloud, Menu, RefreshCw, ChevronLeft } from 'lucide-react';
import { StatusDot, type ConnectionStatus } from '@/components/ui/status-dot';

interface ChatHeaderProps {
  userName?: string;
  connectionStatus: ConnectionStatus;
  onClear: () => void;
  onWhoami: () => void;
  onOpenPalette: () => void;
  onOpenReminders: () => void;
  onOpenDrive: () => void;
  onReconnect: () => void;
  onBack?: () => void;
}

export function ChatHeader({ userName, connectionStatus, onClear, onWhoami, onOpenPalette, onOpenReminders, onOpenDrive, onReconnect, onBack }: ChatHeaderProps) {
  const statusText = connectionStatus === 'online'
    ? 'на связи · слушает'
    : connectionStatus === 'reconnecting'
    ? 'переподключается...'
    : 'офлайн · нажми чтобы переподключиться';
  const statusColorClass = connectionStatus === 'offline' ? 'text-rose' : 'text-gold';

  return (
    <header className="flex items-center justify-between px-4 py-3 border-b border-border-divider bg-bg-base sticky top-0 z-10">
      <div className="flex items-center gap-3">
        {onBack ? (
          <button
            onClick={onBack}
            aria-label="Назад к чату"
            className="h-9 w-9 flex items-center justify-center rounded-button border border-border-subtle bg-bg-deep/50 text-text-secondary hover:text-text-primary hover:border-border-strong transition-colors duration-fast"
          >
            <ChevronLeft size={20} />
          </button>
        ) : (
          <button
            onClick={onOpenPalette}
            aria-label="Меню"
            className="h-9 w-9 flex items-center justify-center rounded-button border border-border-subtle bg-bg-deep/50 text-text-secondary hover:text-text-primary hover:border-border-strong transition-colors duration-fast"
          >
            <Menu size={20} />
          </button>
        )}

        <div className="relative">
          <div className="absolute inset-[-4px] rounded-full bg-gold/10 animate-mira-glow" />
          <img
            src="/mira-avatar-full.png"
            alt="Мира"
            className="relative w-10 h-10 rounded-full object-cover border border-gold-soft"
          />
        </div>

        <div>
          <h1 className="font-serif text-[23px] font-medium text-text-primary leading-tight tracking-wide">Мира</h1>
          {connectionStatus === 'online' ? (
            <div className="flex items-center gap-1.5 mt-0.5">
              <StatusDot status={connectionStatus} />
              <span className={`text-[11px] tracking-wide ${statusColorClass}`}>
                {statusText}
              </span>
            </div>
          ) : (
            <button
              onClick={onReconnect}
              disabled={connectionStatus === 'reconnecting'}
              aria-label="Переподключиться"
              title="Переподключиться к Мире"
              className="flex items-center gap-1.5 mt-0.5 group disabled:opacity-70"
            >
              <StatusDot status={connectionStatus} />
              <span className={`text-[11px] tracking-wide ${statusColorClass} group-hover:underline`}>
                {statusText}
              </span>
              <RefreshCw
                size={11}
                className={`${statusColorClass} ${connectionStatus === 'reconnecting' ? 'animate-spin' : ''}`}
              />
            </button>
          )}
        </div>
      </div>

      <div className="flex items-center gap-1">
        <span className="text-sm text-text-secondary hidden sm:inline mr-2">{userName}</span>
        <button
          onClick={onOpenReminders}
          aria-label="Напоминания"
          className="h-9 w-9 flex items-center justify-center rounded-button border border-border-subtle bg-bg-deep/50 text-text-secondary hover:text-text-primary hover:border-border-strong transition-colors duration-fast"
        >
          <Bell size={20} />
        </button>
        <button
          onClick={onOpenDrive}
          aria-label="Google Drive"
          className="h-9 w-9 flex items-center justify-center rounded-button border border-border-subtle bg-bg-deep/50 text-text-secondary hover:text-text-primary hover:border-border-strong transition-colors duration-fast"
        >
          <Cloud size={20} />
        </button>
        <button
          onClick={onWhoami}
          aria-label="Профиль"
          className="h-9 w-9 flex items-center justify-center rounded-button border border-border-subtle bg-bg-deep/50 text-text-secondary hover:text-text-primary hover:border-border-strong transition-colors duration-fast"
        >
          <User size={20} />
        </button>
        <button
          onClick={onClear}
          aria-label="Очистить историю"
          className="h-9 w-9 flex items-center justify-center rounded-button border border-border-subtle bg-bg-deep/50 text-text-secondary hover:text-rose hover:border-rose/40 transition-colors duration-fast"
        >
          <Trash2 size={20} />
        </button>
      </div>
    </header>
  );
}
