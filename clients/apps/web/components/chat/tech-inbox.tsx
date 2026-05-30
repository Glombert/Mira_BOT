'use client';

import { useState } from 'react';
import type { MiraClient, OwnerInboxItem } from '@mira/shared';

interface TechInboxProps {
  items: OwnerInboxItem[];
  client: MiraClient | null;
  onLocalUpdate: (id: number, patch: Partial<OwnerInboxItem>) => void;
}

const IMPORTANCE_COLORS: Record<string, string> = {
  CRITICAL: 'border-rose/60 bg-rose/5',
  MAJOR:    'border-gold-soft/60 bg-gold/5',
  MINOR:    'border-border-strong bg-bg-deep/40',
  NONE:     'border-border-subtle bg-bg-deep/30',
};

const TYPE_LABEL: Record<string, string> = {
  ritual:           'Ритуал',
  system:           'Система',
  approval_request: 'Заявка',
};

function fmtTime(ts: string): string {
  try {
    const d = new Date(ts);
    return d.toLocaleString('ru-RU', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' });
  } catch {
    return ts;
  }
}

export function TechInbox({ items, client, onLocalUpdate }: TechInboxProps) {
  if (items.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center gap-3 text-text-muted">
        <p className="text-sm font-serif italic">Здесь будет техническая лента: ритуалы, заявки, сбои.</p>
      </div>
    );
  }
  return (
    <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
      {items.map((it) => (
        <InboxCard key={it.id} item={it} client={client} onLocalUpdate={onLocalUpdate} />
      ))}
    </div>
  );
}

function InboxCard({
  item,
  client,
  onLocalUpdate,
}: {
  item: OwnerInboxItem;
  client: MiraClient | null;
  onLocalUpdate: (id: number, patch: Partial<OwnerInboxItem>) => void;
}) {
  const [busy, setBusy] = useState(false);
  const cls = IMPORTANCE_COLORS[item.importance] || IMPORTANCE_COLORS.NONE;
  const label = TYPE_LABEL[item.type] || item.type;

  const apply = async (action: 'approve' | 'reject') => {
    if (!client || busy) return;
    setBusy(true);
    try {
      const r = await client.inboxAction(item.id, action);
      onLocalUpdate(item.id, { action, is_read: true });
      if (!r.ok) {
        console.warn('inboxAction failed', r);
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`rounded-card border px-4 py-3 ${cls} ${item.is_read ? 'opacity-70' : ''}`}>
      <div className="flex items-center justify-between gap-2 mb-1">
        <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-text-secondary">
          <span className="font-medium">{label}</span>
          {item.importance && item.importance !== 'NONE' && (
            <span className="px-1.5 py-0.5 rounded bg-bg-deep/60">{item.importance}</span>
          )}
        </div>
        <span className="text-[11px] text-text-muted">{fmtTime(item.ts)}</span>
      </div>
      {item.title && (
        <p className="text-sm font-medium text-text-primary mb-1">{item.title}</p>
      )}
      <pre className="whitespace-pre-wrap text-sm text-text-secondary font-sans leading-relaxed">{item.body}</pre>

      {item.type === 'approval_request' && !item.action && (
        <div className="flex gap-2 mt-3">
          <button
            disabled={busy}
            onClick={() => apply('approve')}
            className="px-3 py-1.5 text-sm rounded-button bg-gold/20 border border-gold-soft text-gold hover:bg-gold/30 disabled:opacity-50"
          >
            Одобрить
          </button>
          <button
            disabled={busy}
            onClick={() => apply('reject')}
            className="px-3 py-1.5 text-sm rounded-button border border-rose/40 text-rose hover:bg-rose/10 disabled:opacity-50"
          >
            Отклонить
          </button>
        </div>
      )}
      {item.action && (
        <p className="mt-2 text-[11px] text-text-muted">
          {item.action === 'approve' ? '✓ одобрено' : item.action === 'reject' ? '✗ отклонено' : `действие: ${item.action}`}
        </p>
      )}
    </div>
  );
}
