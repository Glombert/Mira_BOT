'use client';

import { useEffect } from 'react';
import { X } from 'lucide-react';
import { ModalShell } from './modal-shell';

interface WhoamiModalProps {
  content: string;
  onClose: () => void;
}

export function WhoamiModal({ content, onClose }: WhoamiModalProps) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const lines = content.split('\n').filter(Boolean);

  return (
    <ModalShell open={!!content} onClose={onClose}>
      <div className="p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-text-primary">Профиль</h2>
          <button
            onClick={onClose}
            aria-label="Закрыть"
            className="h-8 w-8 flex items-center justify-center rounded-button text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors"
          >
            <X size={18} />
          </button>
        </div>
        <div className="space-y-2">
          {lines.map((line, i) => (
            <p key={i} className="text-sm text-text-primary">
              {line}
            </p>
          ))}
        </div>
      </div>
    </ModalShell>
  );
}
