'use client';

import { useEffect, useRef } from 'react';

interface TelegramUser {
  id: number;
  first_name: string;
  last_name?: string;
  username?: string;
  photo_url?: string;
  auth_date: number;
  hash: string;
}

interface TelegramLoginProps {
  botUsername: string;
  mockEnabled: boolean;
  onAuth: (user: {
    id: string;
    first_name: string;
    last_name?: string;
    username?: string;
    photo_url?: string;
    auth_date: string;
    hash: string;
  }) => void;
}

declare global {
  interface Window {
    onTelegramAuth?: (user: TelegramUser) => void;
  }
}

export function TelegramLogin({ botUsername, mockEnabled, onAuth }: TelegramLoginProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;

    const script = document.createElement('script');
    script.src = 'https://telegram.org/js/telegram-widget.js?22';
    script.async = true;
    script.setAttribute('data-telegram-login', botUsername);
    script.setAttribute('data-size', 'large');
    script.setAttribute('data-onauth', 'onTelegramAuth(user)');
    script.setAttribute('data-request-access', 'write');
    script.setAttribute('data-userpic', 'false');

    containerRef.current.innerHTML = '';
    containerRef.current.appendChild(script);

    window.onTelegramAuth = (user) => {
      onAuth({
        id: String(user.id),
        first_name: user.first_name || '',
        last_name: user.last_name,
        username: user.username,
        photo_url: user.photo_url,
        auth_date: String(user.auth_date),
        hash: user.hash,
      });
    };

    return () => {
      if (containerRef.current) {
        containerRef.current.innerHTML = '';
      }
      window.onTelegramAuth = undefined;
    };
  }, [botUsername, onAuth]);

  return (
    <div className="flex flex-col items-center gap-4">
      <div className="flex flex-col items-center gap-2">
        <div className="flex items-center gap-3">
          <svg width="40" height="40" viewBox="0 0 28 28" fill="none" className="shrink-0">
            <defs>
              <linearGradient id="starGrad" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse">
                <stop stopColor="#FF8C42" />
                <stop offset="1" stopColor="#FFB888" />
              </linearGradient>
            </defs>
            <path
              d="M14 2L16.5 11.5H26L18.5 17L21 26L14 21L7 26L9.5 17L2 11.5H11.5L14 2Z"
              fill="url(#starGrad)"
            />
          </svg>
          <h1 className="text-2xl font-semibold text-text-primary">Мира</h1>
        </div>
        <p className="text-sm text-text-secondary">Войди через Telegram, чтобы начать</p>
      </div>
      <div ref={containerRef} />
      {mockEnabled && (
        <button
          onClick={() =>
            onAuth({
              id: '12345',
              first_name: 'Andrey',
              auth_date: String(Math.floor(Date.now() / 1000)),
              hash: 'mockhash',
            })
          }
          className="text-xs text-text-muted hover:text-text-secondary transition-colors"
        >
          Пропустить авторизацию (dev)
        </button>
      )}
    </div>
  );
}
