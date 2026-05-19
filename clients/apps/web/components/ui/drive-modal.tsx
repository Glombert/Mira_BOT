'use client';

import { useState, useEffect } from 'react';
import { X, Cloud, Link2, FolderOpen, Download, Loader2 } from 'lucide-react';
import { ModalShell } from './modal-shell';
import { MiraClient } from '@mira/shared';

interface DriveModalProps {
  open: boolean;
  onClose: () => void;
  client: MiraClient | null;
}

export function DriveModal({ open, onClose, client }: DriveModalProps) {
  const [folder, setFolder] = useState('');
  const [fileId, setFileId] = useState('');
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [authUrl, setAuthUrl] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setFolder('');
      setFileId('');
      setResult(null);
      setAuthUrl(null);
      setLoading(false);
    }
  }, [open]);

  const run = async (cmd: string, expectedTypes?: string[]) => {
    if (!client) return;
    setLoading(true);
    setResult(null);
    setAuthUrl(null);
    try {
      const types = (expectedTypes || ['system', 'gdrive_auth_url']) as any;
      const msg = await client.sendCommandAwait(cmd, types, 15000);
      if (msg.type === 'gdrive_auth_url') {
        setAuthUrl(msg.url);
      } else if ('content' in msg) {
        setResult(msg.content);
      }
    } catch {
      setResult('Ошибка: нет ответа от сервера');
    } finally {
      setLoading(false);
    }
  };

  return (
    <ModalShell open={open} onClose={onClose}>
      <div className="p-6 max-h-[85vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-text-primary flex items-center gap-2">
            <Cloud size={20} className="text-accent" />
            Google Drive
          </h2>
          <button onClick={onClose} aria-label="Закрыть" className="h-8 w-8 flex items-center justify-center rounded-button text-text-secondary hover:text-text-primary hover:bg-bg-elevated transition-colors">
            <X size={18} />
          </button>
        </div>

        <div className="space-y-3">
          <button
            onClick={() => run('gdrive_login')}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-button bg-bg-elevated text-text-primary hover:bg-bg-input transition-colors text-sm border border-border-default"
          >
            <Link2 size={16} />
            Привязать Google Drive
          </button>

          <button
            onClick={() => run('gdrive_status')}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-button bg-bg-elevated text-text-primary hover:bg-bg-input transition-colors text-sm border border-border-default"
          >
            <Cloud size={16} />
            Статус привязки
          </button>

          <div className="bg-bg-elevated rounded-card p-3 space-y-2">
            <h3 className="text-sm font-medium text-text-primary">Список файлов</h3>
            <div className="flex items-center gap-2">
              <input
                value={folder}
                onChange={(e) => setFolder(e.target.value)}
                placeholder="Папка (опционально)"
                className="flex-1 bg-bg-input border border-border-default rounded-input px-3 py-2 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-border-focus focus:shadow-glow"
              />
              <button
                onClick={() => run(folder ? `gdrive_list ${folder}` : 'gdrive_list')}
                className="px-3 py-2 rounded-button bg-accent text-text-on-accent hover:bg-accent-hover shadow-glow transition-colors text-sm"
              >
                <FolderOpen size={16} />
              </button>
            </div>
          </div>

          <div className="bg-bg-elevated rounded-card p-3 space-y-2">
            <h3 className="text-sm font-medium text-text-primary">Скачать файл</h3>
            <div className="flex items-center gap-2">
              <input
                value={fileId}
                onChange={(e) => setFileId(e.target.value)}
                placeholder="ID файла"
                className="flex-1 bg-bg-input border border-border-default rounded-input px-3 py-2 text-sm text-text-primary placeholder:text-text-muted outline-none focus:border-border-focus focus:shadow-glow"
              />
              <button
                onClick={() => {
                  if (fileId) run(`gdrive_get ${fileId}`);
                }}
                className="px-3 py-2 rounded-button bg-accent text-text-on-accent hover:bg-accent-hover shadow-glow transition-colors text-sm"
              >
                <Download size={16} />
              </button>
            </div>
          </div>

          {loading && (
            <div className="flex items-center justify-center gap-2 py-2">
              <Loader2 size={16} className="animate-spin text-accent" />
              <span className="text-sm text-text-secondary">Жду ответа...</span>
            </div>
          )}

          {authUrl && (
            <div className="bg-bg-input rounded-card p-3 border border-border-default">
              <p className="text-sm text-text-primary mb-2">Открой эту ссылку для авторизации:</p>
              <a
                href={authUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm text-accent hover:text-accent-hover underline break-all"
              >
                {authUrl}
              </a>
            </div>
          )}

          {result && (
            <div className="bg-bg-input rounded-card p-3 border border-border-default">
              <pre className="text-sm text-text-primary whitespace-pre-wrap font-sans">{result}</pre>
            </div>
          )}
        </div>
      </div>
    </ModalShell>
  );
}
