'use client';

import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { FileText, Folder, Cloud } from 'lucide-react';
import { formatBytes } from '@/lib/utils';

function formatTime(ts: number): string {
  if (!ts) return '';
  const d = new Date(ts);
  const now = new Date();
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  if (d.toDateString() === now.toDateString()) return `${hh}:${mm}`;
  const y = new Date(now.getTime() - 86400000);
  if (d.toDateString() === y.toDateString()) return `вчера ${hh}:${mm}`;
  const months = ['янв','фев','мар','апр','мая','июн','июл','авг','сен','окт','ноя','дек'];
  return `${d.getDate()} ${months[d.getMonth()]} ${hh}:${mm}`;
}

function isFresh(ts: number) {
  return Date.now() - ts < 5000;
}

function TypewriterText({ content }: { content: string }) {
  const [displayed, setDisplayed] = React.useState('');
  React.useEffect(() => {
    let idx = 0;
    const total = content.length;
    const interval = setInterval(() => {
      idx += 1;
      if (idx >= total) {
        setDisplayed(content);
        clearInterval(interval);
      } else {
        setDisplayed(content.slice(0, idx));
      }
    }, 33);
    return () => clearInterval(interval);
  }, [content]);
  return <>{displayed}</>;
}
import type { ServerMessage } from '@mira/shared';

export interface ChatMessageItem {
  id: string;
  type: ServerMessage['type'] | 'user';
  content?: string;
  url?: string;
  files?: Array<{ name: string; dir: string; size: number }>;
  attachments?: Array<{ name: string; dir: string; size: number }>;
  messageAttachments?: Array<{ name: string; size: number }>;
  approval?: { user_id: string; name: string; source: string };
  timestamp: number;
}

interface ChatMessageProps {
  message: ChatMessageItem;
  getFileUrl?: (dir: 'inbox' | 'output', name: string) => string;
  onApprove?: (userId: string) => void;
  onBlock?: (userId: string) => void;
}

export function ChatMessageBubble({ message, getFileUrl, onApprove, onBlock }: ChatMessageProps) {
  const { type, content, url, files } = message;

  if (type === 'user') {
    return (
      <div className="flex flex-col items-end animate-fade-in-up gap-1">
        <div className="max-w-[70%] rounded-card rounded-br-button bg-bg-elevated px-4 py-3 text-text-primary text-base leading-relaxed">
          {content}
        </div>
        {message.timestamp ? <span className="text-[11px] text-text-muted mr-1">{formatTime(message.timestamp)}</span> : null}
      </div>
    );
  }

  if (type === 'thinking') {
    return (
      <div className="flex items-start gap-3 animate-fade-in-up">
        <img src="/mira-avatar-full.png" alt="Мира" className="w-7 h-7 rounded-full object-cover shrink-0" />
        <div className="flex items-center gap-2 px-4 py-3">
          <span className="h-2 w-2 rounded-full bg-accent animate-pulse-think" />
          <span className="h-2 w-2 rounded-full bg-accent animate-pulse-think [animation-delay:200ms]" />
          <span className="h-2 w-2 rounded-full bg-accent animate-pulse-think [animation-delay:400ms]" />
        </div>
      </div>
    );
  }

  if (type === 'system') {
    return (
      <div className="flex items-center justify-center gap-2 py-1 animate-fade-in-up">
        <span className="text-sm text-text-secondary whitespace-pre-wrap">{content}</span>
      </div>
    );
  }

  if (type === 'error') {
    return (
      <div className="flex items-center justify-center gap-2 py-1 animate-fade-in-up">
        <span className="text-sm text-error whitespace-pre-wrap">{content}</span>
      </div>
    );
  }

  if (type === 'message') {
    const isNew = isFresh(message.timestamp);
    return (
      <div className="flex items-start gap-3 animate-fade-in-up">
        <img src="/mira-avatar-full.png" alt="Мира" className="w-7 h-7 rounded-full object-cover shrink-0" />
        <div className="flex-1 min-w-0">
          <span className="text-xs text-text-secondary mb-1 block">Мира</span>
          <div className="text-text-primary text-base leading-relaxed">
            {isNew ? (
              <TypewriterText content={content || ''} />
            ) : (
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                className="mira-markdown"
                components={{
                  a: ({ href, children }) => {
                    const allowed = ['http:', 'https:', 'mailto:', 'tg:'];
                    let safe = href || '#';
                    try {
                      const u = new URL(safe, window.location.href);
                      if (!allowed.includes(u.protocol)) safe = '#';
                    } catch {
                      safe = '#';
                    }
                    return (
                      <a href={safe} target="_blank" rel="noopener noreferrer">
                        {children}
                      </a>
                    );
                  },
                }}
              >
                {content || ''}
              </ReactMarkdown>
            )}
          </div>
          {message.messageAttachments && message.messageAttachments.length > 0 && (
            <div className="mt-2 space-y-1">
              {message.messageAttachments.map((a, i) => (
                <span key={i}
                   className="inline-flex items-center gap-2 bg-bg-base border border-border-focus rounded-lg px-3 py-1.5 text-sm text-accent-secondary">
                  <FileText size={14} />
                  <span className="truncate">{a.name}</span>
                  <span className="text-text-muted text-xs">{formatBytes(a.size)}</span>
                </span>
              ))}
            </div>
          )}
          {message.timestamp ? <span className="text-[11px] text-text-muted mt-1 block">{formatTime(message.timestamp)}</span> : null}
        </div>
      </div>
    );
  }

  if (type === 'approval_request' && message.approval) {
    const [resolved, setResolved] = React.useState<'approve' | 'block' | null>(null);
    const a = message.approval;
    if (resolved === 'approve') {
      return (
        <div className="flex justify-center animate-fade-in-up">
          <div className="max-w-[70%] bg-status-online/10 border border-status-online/30 rounded-card px-4 py-2 text-sm text-status-online">
            ✅ Пользователь {a.name} одобрен
          </div>
        </div>
      );
    }
    if (resolved === 'block') {
      return (
        <div className="flex justify-center animate-fade-in-up">
          <div className="max-w-[70%] bg-status-offline/10 border border-status-offline/30 rounded-card px-4 py-2 text-sm text-status-offline">
            ❌ Пользователь {a.name} заблокирован
          </div>
        </div>
      );
    }
    return (
      <div className="flex justify-center animate-fade-in-up">
        <div className="max-w-[80%] bg-bg-elevated border border-border-default rounded-card px-4 py-3 space-y-2">
          <p className="text-sm text-text-secondary">Новый пользователь запрашивает доступ:</p>
          <p className="text-base text-text-primary font-medium">{a.name} <span className="text-text-muted text-sm">({a.source})</span></p>
          <div className="flex gap-2">
            <button
              onClick={() => { setResolved('approve'); onApprove?.(a.user_id); }}
              className="flex-1 bg-status-online/20 hover:bg-status-online/30 text-status-online rounded-button px-3 py-1.5 text-sm font-medium transition-colors"
            >
              Одобрить
            </button>
            <button
              onClick={() => { setResolved('block'); onBlock?.(a.user_id); }}
              className="flex-1 bg-status-offline/20 hover:bg-status-offline/30 text-status-offline rounded-button px-3 py-1.5 text-sm font-medium transition-colors"
            >
              Заблокировать
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (type === 'gdrive_auth_url' && url) {
    return (
      <div className="flex items-center justify-center gap-2 py-1 animate-fade-in-up">
        <Cloud size={16} className="text-accent shrink-0" />
        <a
          href={url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-accent hover:text-accent-hover underline"
        >
          Привязать Google Drive
        </a>
      </div>
    );
  }

  if (type === 'files' && files) {
    return (
      <div className="flex justify-center animate-fade-in-up">
        <div className="max-w-[70%] bg-bg-elevated rounded-card px-4 py-3 space-y-2">
          <p className="text-sm text-text-secondary font-medium">Файлы</p>
          {files.map((f) => (
            <div key={f.name} className="flex items-center gap-2 text-sm text-text-primary">
              {f.dir === 'inbox' ? <FileText size={16} className="text-text-secondary shrink-0" /> : <Folder size={16} className="text-text-secondary shrink-0" />}
              {getFileUrl ? (
                <a
                  href={getFileUrl(f.dir as 'inbox' | 'output', f.name)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="truncate text-accent hover:text-accent-hover underline"
                >
                  {f.name}
                </a>
              ) : (
                <span className="truncate">{f.name}</span>
              )}
              <span className="text-text-muted text-xs shrink-0">{formatBytes(f.size)}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // fallback for any other types
  return (
    <div className="flex items-center justify-center gap-2 py-1 animate-fade-in-up">
      <span className="text-sm text-text-secondary whitespace-pre-wrap">{content || JSON.stringify(message)}</span>
    </div>
  );
}


