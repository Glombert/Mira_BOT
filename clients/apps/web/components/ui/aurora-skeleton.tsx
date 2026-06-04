'use client';

import React from 'react';

export function AuroraSkeleton({ className = '' }: { className?: string }) {
  return (
    <div className={`animate-pulse ${className}`}>
      <div className="h-4 bg-white/[0.04] rounded mb-2" style={{ width: '60%' }} />
      <div className="h-4 bg-white/[0.04] rounded mb-2" style={{ width: '80%' }} />
      <div className="h-4 bg-white/[0.04] rounded" style={{ width: '40%' }} />
    </div>
  );
}

export function AuroraEmpty({ message = 'Пусто' }: { message?: string }) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3 text-text-muted">
      <svg width="48" height="48" viewBox="0 0 28 28" fill="none">
        <defs>
          <linearGradient id="emptyStar" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse">
            <stop stopColor="#f5bc7a" stopOpacity="0.3" />
            <stop offset="1" stopColor="#f8cfa0" stopOpacity="0.2" />
          </linearGradient>
        </defs>
        <path d="M14 2L16.5 11.5H26L18.5 17L21 26L14 21L7 26L9.5 17L2 11.5H11.5L14 2Z" fill="url(#emptyStar)" />
      </svg>
      <p className="text-sm text-text-secondary font-serif italic">{message}</p>
    </div>
  );
}

export function AuroraError({ message = 'Ошибка загрузки', onRetry }: { message?: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3">
      <div
        className="px-5 py-4 rounded-xl text-center"
        style={{ border: '1px solid rgba(232,138,138,0.30)', background: 'rgba(232,138,138,0.06)' }}
      >
        <p className="text-sm text-rose mb-2">{message}</p>
        {onRetry && (
          <button
            onClick={onRetry}
            className="text-xs text-rose hover:underline"
          >
            Попробовать снова
          </button>
        )}
      </div>
    </div>
  );
}
