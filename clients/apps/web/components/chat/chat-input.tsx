'use client';

import { useState, useRef, useCallback } from 'react';
import { Send, Paperclip, X } from 'lucide-react';
import { cn } from '@/lib/utils';

interface ChatInputProps {
  onSend: (text: string) => void;
  onFileSelect?: (file: File) => void;
  disabled?: boolean;
  placeholder?: string;
  pendingAttachment?: { name: string; size: number } | null;
  onClearAttachment?: () => void;
  uploading?: boolean;
}

export function ChatInput({
  onSend,
  onFileSelect,
  disabled,
  placeholder = 'Напиши Мире...',
  pendingAttachment,
  onClearAttachment,
  uploading,
}: ChatInputProps) {
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleSend = useCallback(() => {
    const trimmed = text.trim();
    if ((!trimmed && !pendingAttachment) || disabled || uploading) return;
    onSend(trimmed);
    setText('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  }, [text, disabled, uploading, pendingAttachment, onSend]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setText(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 160) + 'px';
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && onFileSelect) {
      onFileSelect(file);
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div className="space-y-2">
      {pendingAttachment && (
        <div className="flex items-center gap-2 bg-bg-elevated border border-border-focus rounded-lg px-3 py-1.5 text-sm">
          <span className="text-accent-secondary truncate">📎 {pendingAttachment.name}</span>
          <button onClick={onClearAttachment} className="text-text-muted hover:text-text-primary ml-auto">
            <X size={14} />
          </button>
        </div>
      )}
      <div className="flex items-end gap-2 bg-bg-elevated border border-border-default rounded-input p-2 focus-within:border-border-focus focus-within:shadow-glow transition-all duration-fast">
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled || uploading}
          aria-label="Прикрепить файл"
          className="h-9 w-9 flex items-center justify-center rounded-button text-text-secondary hover:text-text-primary hover:bg-bg-overlay transition-colors duration-fast shrink-0"
        >
          {uploading ? <span className="animate-spin text-accent">⟳</span> : <Paperclip size={18} />}
        </button>
        <input ref={fileInputRef} type="file" className="hidden" onChange={handleFileChange} />
        <textarea
          ref={textareaRef}
          value={text}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          disabled={disabled || uploading}
          rows={1}
          className="flex-1 bg-transparent text-text-primary placeholder:text-text-muted resize-none outline-none text-base px-2 py-1.5 max-h-[160px] min-h-[40px]"
          placeholder={disabled ? 'Подключение...' : placeholder}
        />
        <button
          onClick={handleSend}
          disabled={(!text.trim() && !pendingAttachment) || disabled || uploading}
          aria-label="Отправить"
          className={cn(
            'flex items-center justify-center h-9 w-9 rounded-button transition-colors duration-fast shrink-0',
            (text.trim() || pendingAttachment) && !disabled
              ? 'bg-accent text-text-on-accent hover:bg-accent-hover shadow-glow'
              : 'bg-bg-overlay text-text-muted'
          )}
        >
          <Send size={18} />
        </button>
      </div>
    </div>
  );
}
