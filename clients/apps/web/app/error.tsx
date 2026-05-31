'use client';

// Error Boundary маршрута (Next app router): ловит ошибку рендера вместо белого
// экрана и даёт пользователю переподключиться/перезагрузить.

import { useEffect } from 'react';

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // В консоль (и в Sentry, если подключён на клиенте позже)
    console.error('Mira UI error:', error);
  }, [error]);

  return (
    <div className="min-h-[100dvh] flex flex-col items-center justify-center gap-4 px-6 bg-bg-base text-text-primary text-center">
      <h1 className="font-serif text-2xl text-accent">Что-то сломалось</h1>
      <p className="text-sm text-text-secondary max-w-sm">
        Мира столкнулась с непредвиденной ошибкой в интерфейсе. Это не потеряло твои данные —
        можно просто попробовать снова.
      </p>
      <div className="flex gap-3">
        <button
          onClick={reset}
          className="rounded-button bg-accent px-5 py-2.5 font-medium text-text-on-accent hover:bg-accent-hover transition-colors"
        >
          Попробовать снова
        </button>
        <button
          onClick={() => window.location.reload()}
          className="rounded-button border border-border-strong px-5 py-2.5 text-text-secondary hover:text-text-primary transition-colors"
        >
          Перезагрузить
        </button>
      </div>
    </div>
  );
}
