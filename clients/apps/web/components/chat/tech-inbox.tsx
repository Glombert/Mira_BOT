'use client';

import { useEffect, useRef, useState } from 'react';
import type { MiraClient, OwnerInboxItem } from '@mira/shared';

/** Запись в технической ленте — либо событие из owner_inbox, либо реплика
 *  переписки с Мирой в tech-режиме. */
export type TechFeedEntry =
  | { kind: 'inbox'; ts: number; item: OwnerInboxItem }
  | { kind: 'msg'; ts: number; role: 'user' | 'assistant'; content: string }
  | { kind: 'thinking'; ts: number }
  | { kind: 'error'; ts: number; content: string };

interface TechChatProps {
  feed: TechFeedEntry[];
  client: MiraClient | null;
  onLocalUpdate: (id: number, patch: Partial<OwnerInboxItem>) => void;
  onSend: (text: string) => void;
  sending: boolean;
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

function fmtTime(ts: number | string): string {
  try {
    const d = typeof ts === 'number' ? new Date(ts) : new Date(ts);
    return d.toLocaleString('ru-RU', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' });
  } catch {
    return String(ts);
  }
}

export function TechInbox({ feed, client, onLocalUpdate, onSend, sending }: TechChatProps) {
  const [draft, setDraft] = useState('');
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [feed]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const t = draft.trim();
    if (!t || sending) return;
    onSend(t);
    setDraft('');
  };

  return (
    <>
      <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
        {feed.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-text-muted">
            <p className="text-sm font-serif italic">
              Технический канал. Здесь оповещения о ритуалах/сбоях и закрытый разговор с Мирой.
            </p>
          </div>
        )}
        {feed.map((entry, idx) => {
          if (entry.kind === 'inbox') {
            return <InboxCard key={`i-${entry.item.id}-${idx}`} item={entry.item} client={client} onLocalUpdate={onLocalUpdate} />;
          }
          if (entry.kind === 'thinking') {
            return (
              <div key={`t-${idx}`} className="text-sm text-text-muted italic">
                Мира думает...
              </div>
            );
          }
          if (entry.kind === 'error') {
            return (
              <div key={`e-${idx}`} className="text-sm text-rose">
                {entry.content}
              </div>
            );
          }
          // msg
          const mine = entry.role === 'user';
          return (
            <div key={`m-${idx}`} className={`flex ${mine ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[85%] rounded-card px-3 py-2 text-sm whitespace-pre-wrap ${
                  mine ? 'bg-gold/10 border border-gold-soft/40 text-text-primary' : 'bg-bg-deep/40 border border-border-subtle text-text-secondary'
                }`}
              >
                {entry.content}
              </div>
            </div>
          );
        })}
        <div ref={endRef} />
      </div>
      <form
        onSubmit={handleSubmit}
        className="px-4 py-3 border-t border-border-subtle bg-bg-base flex gap-2"
      >
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Технический вопрос Мире..."
          disabled={sending}
          className="flex-1 bg-bg-deep/40 border border-border-subtle rounded-button px-3 py-2 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-gold-soft disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={!draft.trim() || sending}
          className="px-4 py-2 text-sm rounded-button bg-gold/20 border border-gold-soft text-gold hover:bg-gold/30 disabled:opacity-50"
        >
          {sending ? '...' : 'Отправить'}
        </button>
      </form>
    </>
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
