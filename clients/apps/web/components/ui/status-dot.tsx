'use client';

import { cn } from '@/lib/utils';

export type ConnectionStatus = 'online' | 'reconnecting' | 'offline';

interface StatusDotProps {
  status: ConnectionStatus;
  className?: string;
}

export function StatusDot({ status, className }: StatusDotProps) {
  return (
    <span
      className={cn(
        'inline-block h-2 w-2 rounded-full',
        status === 'online' && 'bg-success',
        status === 'reconnecting' && 'bg-warning animate-pulse',
        status === 'offline' && 'bg-text-muted',
        className
      )}
      aria-hidden="true"
    />
  );
}
