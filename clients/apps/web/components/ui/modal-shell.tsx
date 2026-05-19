'use client';

import { cn } from '@/lib/utils';

interface ModalShellProps {
  open: boolean;
  onClose: () => void;
  children: React.ReactNode;
  className?: string;
}

export function ModalShell({ open, onClose, children, className }: ModalShellProps) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex sm:items-center sm:justify-center items-end justify-center px-0 sm:px-4"
      role="dialog"
      aria-modal="true"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div
        className={cn(
          'relative w-full max-w-lg bg-bg-overlay shadow-elevated overflow-hidden animate-fade-in-up',
          'sm:rounded-card rounded-t-card',
          'sm:max-h-none max-h-[90vh] overflow-y-auto',
          className
        )}
      >
        {/* Drag handle for mobile */}
        <div className="sm:hidden flex justify-center pt-2 pb-1">
          <div className="w-10 h-1 rounded-full bg-text-muted/40" />
        </div>
        {children}
      </div>
    </div>
  );
}
