'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { StarAvatar } from '@/components/ui/star-avatar';
import { FileText, Folder, Cloud } from 'lucide-react';
import { formatBytes } from '@/lib/utils';
import type { ServerMessage } from '@mira/shared';

export interface ChatMessageItem {
  id: string;
  type: ServerMessage['type'] | 'user';
  content?: string;
  url?: string;
  files?: Array<{ name: string; dir: string; size: number }>;
  timestamp: number;
}

interface ChatMessageProps {
  message: ChatMessageItem;
  getFileUrl?: (dir: 'inbox' | 'output', name: string) => string;
}

export function ChatMessageBubble({ message, getFileUrl }: ChatMessageProps) {
  const { type, content, url, files } = message;

  if (type === 'user') {
    return (
      <div className="flex justify-end animate-fade-in-up">
        <div className="max-w-[70%] rounded-card rounded-br-button bg-bg-elevated px-4 py-3 text-text-primary text-base leading-relaxed">
          {content}
        </div>
      </div>
    );
  }

  if (type === 'thinking') {
    return (
      <div className="flex items-start gap-3 animate-fade-in-up">
        <StarAvatar size={28} />
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
    return (
      <div className="flex items-start gap-3 animate-fade-in-up">
        <StarAvatar size={28} />
        <div className="flex-1 min-w-0">
          <span className="text-xs text-text-secondary mb-1 block">Мира</span>
          <div className="text-text-primary text-base leading-relaxed">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              className="mira-markdown"
              components={{
                a: ({ href, children }) => (
                  <a href={href} target="_blank" rel="noopener noreferrer">
                    {children}
                  </a>
                ),
              }}
            >
              {content || ''}
            </ReactMarkdown>
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


