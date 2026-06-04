'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { SectionHeader, PrimaryBtn, ChipToggle, ScreenShell } from './screen-primitives';
import { Spark } from '../chat/aurora-cards';
import type { MiraClient } from '@mira/shared';

interface FileItem {
  id: string;
  name: string;
  kind: 'doc' | 'pdf' | 'img' | 'sheet' | 'audio' | 'zip';
  size: string;
  updatedAt: string;
  loc: 'cloud' | 'local';
  miraNote?: string;
}

const FILE_KINDS: Record<string, { color: string; label: string; glyph: (c: string) => React.ReactNode }> = {
  doc: { color: '#7aa6f5', label: 'документ', glyph: (c) => <svg width="20" height="20" viewBox="0 0 16 16" fill="none"><path d="M3 3 H12 A1 1 0 0 1 13 4 V13 A1 1 0 0 1 12 14 H3 Z" stroke={c} strokeWidth="1.1"/><path d="M3 3 V14" stroke={c} strokeWidth="1.1"/><path d="M5.5 6 H10.5 M5.5 8.5 H10.5 M5.5 11 H9" stroke={c} strokeWidth="0.9" strokeOpacity="0.6"/></svg> },
  pdf: { color: '#e88a8a', label: 'PDF', glyph: (c) => <svg width="20" height="20" viewBox="0 0 16 16" fill="none"><path d="M4 2 H10 L13 5 V13 A1 1 0 0 1 12 14 H4 A1 1 0 0 1 3 13 V3 A1 1 0 0 1 4 2 Z" stroke={c} strokeWidth="1.1" strokeLinejoin="round"/><path d="M10 2 V5 H13" stroke={c} strokeWidth="1.1"/><path d="M5.5 9 H8.5 M5.5 11.5 H7" stroke={c} strokeWidth="0.9" strokeOpacity="0.6"/></svg> },
  img: { color: '#b9a3ff', label: 'изображение', glyph: (c) => <svg width="20" height="20" viewBox="0 0 16 16" fill="none"><rect x="2.5" y="3" width="11" height="10" rx="1.2" stroke={c} strokeWidth="1.1"/><circle cx="6" cy="6.5" r="1" stroke={c} strokeWidth="1"/><path d="M3 11 L6 8.5 L9 11 L11.5 9 L13 10.5" stroke={c} strokeWidth="1.1" strokeLinejoin="round" strokeLinecap="round"/></svg> },
  sheet: { color: '#8dd0a7', label: 'таблица', glyph: (c) => <svg width="20" height="20" viewBox="0 0 16 16" fill="none"><rect x="2.5" y="3" width="11" height="10" rx="0.8" stroke={c} strokeWidth="1.1"/><path d="M2.5 6.5 H13.5 M2.5 9.5 H13.5 M6 3 V13 M10 3 V13" stroke={c} strokeWidth="0.9" strokeOpacity="0.8"/></svg> },
  audio: { color: '#f5bc7a', label: 'аудио', glyph: (c) => <svg width="20" height="20" viewBox="0 0 16 16" fill="none"><path d="M4 11 V8 A4 4 0 0 1 12 8 V11 L13 12 H3 Z M7 13.5 A1 1 0 0 0 9 13.5" stroke={c} strokeWidth="1.1" strokeLinejoin="round" strokeLinecap="round"/></svg> },
  zip: { color: 'rgba(244,234,214,0.62)', label: 'архив', glyph: (c) => <svg width="20" height="20" viewBox="0 0 16 16" fill="none"><path d="M2 5 V12 A1 1 0 0 0 3 13 H13 A1 1 0 0 0 14 12 V6 A1 1 0 0 0 13 5 H8 L6.5 3 H3 A1 1 0 0 0 2 4 Z" stroke={c} strokeWidth="1.1" strokeLinejoin="round"/></svg> },
};

function LocBadge({ loc }: { loc: 'cloud' | 'local' }) {
  if (loc === 'cloud') {
    return (
      <div
        className="inline-flex items-center gap-1.5 h-[22px] px-2 rounded-pill text-[10px] tracking-wide"
        style={{
          background: 'rgba(141,208,167,0.10)',
          border: '1px solid rgba(141,208,167,0.30)',
          color: '#8dd0a7',
        }}
      >
        <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M4 11 A2.5 2.5 0 0 1 4 6 A3.5 3.5 0 0 1 11 6.5 A2.5 2.5 0 0 1 12 11 Z" stroke="currentColor" strokeWidth="1.1" strokeLinejoin="round"/></svg>
        облако
      </div>
    );
  }
  return (
    <div
      className="inline-flex items-center gap-1.5 h-[22px] px-2 rounded-pill text-[10px] tracking-wide"
      style={{
        background: 'rgba(122,166,245,0.10)',
        border: '1px solid rgba(122,166,245,0.32)',
        color: '#7aa6f5',
      }}
    >
      <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><rect x="2.5" y="3" width="11" height="7.5" rx="1" stroke="currentColor" strokeWidth="1.15"/><path d="M6 13 H10 M8 10.5 V13" stroke="currentColor" strokeWidth="1.15" strokeLinecap="round"/></svg>
      локально
    </div>
  );
}

function FileCard({ f }: { f: FileItem }) {
  const kind = FILE_KINDS[f.kind] || FILE_KINDS.doc;
  const isCloud = f.loc === 'cloud';
  return (
    <div
      className="flex flex-col gap-3 p-4 rounded-xl relative"
      style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(244,234,214,0.10)' }}
    >
      <div className="flex items-start justify-between">
        <div
          className="w-11 h-11 rounded-lg flex items-center justify-center"
          style={{ background: `${kind.color}14`, border: `1px solid ${kind.color}40`, color: kind.color }}
        >
          {kind.glyph(kind.color)}
        </div>
        <LocBadge loc={f.loc} />
      </div>
      <div className="flex-1">
        <div className="text-[13px] font-medium leading-snug line-clamp-2" style={{ color: '#f4ead6' }}>{f.name}</div>
        <div className="flex gap-2 mt-1 text-[10.5px] font-mono tracking-wide" style={{ color: 'rgba(244,234,214,0.36)' }}>
          <span style={{ color: kind.color, opacity: 0.8 }}>{kind.label}</span>
          <span>·</span><span>{f.size}</span>
          <span>·</span><span>{f.updatedAt}</span>
        </div>
      </div>
      {f.miraNote && (
        <div className="flex gap-2 items-start">
          <span className="text-gold shrink-0 mt-0.5"><Spark size={9} color="#f5bc7a" /></span>
          <span className="font-serif italic text-xs leading-snug" style={{ color: 'rgba(244,234,214,0.62)' }}>{f.miraNote}</span>
        </div>
      )}
      <div className="flex items-center gap-2 pt-3" style={{ borderTop: '1px solid rgba(244,234,214,0.06)' }}>
        <button
          className="flex-1 h-8 rounded-md text-xs tracking-wide inline-flex items-center justify-center gap-1.5 transition-colors"
          style={{
            background: isCloud ? 'rgba(255,255,255,0.03)' : 'rgba(245,188,122,0.10)',
            border: `1px solid ${isCloud ? 'rgba(244,234,214,0.10)' : 'rgba(245,188,122,0.30)'}`,
            color: isCloud ? '#f4ead6' : '#f5bc7a',
          }}
        >
          {isCloud ? (
            <><svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M8 2 V10 M5 7.5 L8 10.5 L11 7.5 M3.5 13 H12.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg> Скачать</>
          ) : (
            <><svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M4.5 12 A2.3 2.3 0 0 1 4.5 7.4 A3.3 3.3 0 0 1 11 7.9 A2.3 2.3 0 0 1 11.5 12" stroke="currentColor" strokeWidth="1.15" strokeLinejoin="round"/><path d="M8 13.5 V7.5 M6 9.3 L8 7.2 L10 9.3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg> В облако</>
          )}
        </button>
        <button className="w-8 h-8 rounded-md inline-flex items-center justify-center" style={{ border: '1px solid rgba(244,234,214,0.10)', color: 'rgba(244,234,214,0.36)' }}>
          <svg width="16" height="16" viewBox="0 0 18 18" fill="none"><circle cx="9" cy="4" r="1.1" fill="currentColor"/><circle cx="9" cy="9" r="1.1" fill="currentColor"/><circle cx="9" cy="14" r="1.1" fill="currentColor"/></svg>
        </button>
      </div>
    </div>
  );
}

function UploadZone() {
  return (
    <div
      className="min-h-[192px] p-7 rounded-xl flex flex-col items-center justify-center gap-2.5 text-center cursor-pointer transition-colors hover:bg-gold/[0.04]"
      style={{
        border: '1.5px dashed rgba(245,188,122,0.30)',
        background: 'rgba(245,188,122,0.03)',
      }}
    >
      <div
        className="w-11 h-11 rounded-full flex items-center justify-center"
        style={{ background: 'rgba(245,188,122,0.08)', border: '1px solid rgba(245,188,122,0.30)', color: '#f5bc7a' }}
      >
        <svg width="18" height="18" viewBox="0 0 16 16" fill="none"><path d="M4.5 12 A2.3 2.3 0 0 1 4.5 7.4 A3.3 3.3 0 0 1 11 7.9 A2.3 2.3 0 0 1 11.5 12" stroke="currentColor" strokeWidth="1.15" strokeLinejoin="round"/><path d="M8 13.5 V7.5 M6 9.3 L8 7.2 L10 9.3" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>
      </div>
      <div>
        <div className="font-serif italic text-[15px]" style={{ color: '#f4ead6' }}>перетащи файл сюда</div>
        <div className="text-[11px] text-text-muted mt-0.5">Мира прочитает, запомнит и сохранит в облако</div>
      </div>
    </div>
  );
}

interface FilesScreenProps {
  client: MiraClient | null;
}

export function FilesScreen({ client }: FilesScreenProps) {
  const [files, setFiles] = useState<FileItem[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!client) return;
    setLoading(true);
    try {
      const msg = await client.sendCommandAwait('files', ['files'], 8000);
      if ('files' in msg && Array.isArray(msg.files)) {
        // Map raw files to FileItem format
        const mapped: FileItem[] = msg.files.map((f: any, i: number) => ({
          id: `${i}`,
          name: f.name,
          kind: guessKind(f.name),
          size: formatSize(f.size || 0),
          updatedAt: 'недавно',
          loc: f.dir === 'inbox' ? 'local' : 'cloud',
        }));
        setFiles(mapped);
      }
    } catch {
      // fallback to empty
    } finally {
      setLoading(false);
    }
  }, [client]);

  useEffect(() => {
    load();
  }, [load]);

  const cloud = files.filter((f) => f.loc === 'cloud').length;
  const local = files.filter((f) => f.loc === 'local').length;

  return (
    <ScreenShell>
      <SectionHeader
        title="Мои файлы"
        subtitle="всё, что ты передал Мире · она читает, помнит и связывает с беседами"
        actions={
          <>
            <PrimaryBtn>
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" className="inline mr-1"><path d="M4 11 A2.5 2.5 0 0 1 4 6 A3.5 3.5 0 0 1 11 6.5 A2.5 2.5 0 0 1 12 11 Z" stroke="currentColor" strokeWidth="1.1" strokeLinejoin="round"/></svg>
              синхронизировать
            </PrimaryBtn>
            <PrimaryBtn gold>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="inline mr-1"><path d="M7 2 V12 M2 7 H12" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>
              загрузить
            </PrimaryBtn>
          </>
        }
      />

      {/* toolbar */}
      <div
        className="flex items-center gap-3 relative z-[2] flex-wrap"
        style={{ padding: '14px 32px', borderBottom: '1px solid rgba(244,234,214,0.06)' }}
      >
        <div className="flex gap-4 text-[11.5px] text-text-muted font-mono">
          <span><span className="text-text-primary">{files.length}</span> файлов</span>
          <span><span style={{ color: '#8dd0a7' }}>{cloud}</span> в облаке</span>
          <span><span style={{ color: '#7aa6f5' }}>{local}</span> локально</span>
        </div>
        <div className="flex-1" />
        <div className="flex gap-1.5">
          <ChipToggle active>все</ChipToggle>
          <ChipToggle>в облаке</ChipToggle>
          <ChipToggle>локально</ChipToggle>
          <ChipToggle>документы</ChipToggle>
        </div>
      </div>

      {/* body */}
      <div className="flex-1 overflow-y-auto mira-scroll" style={{ padding: '24px 32px 40px' }}>
        {loading ? (
          <div className="text-center text-text-muted text-sm py-10">Загрузка файлов…</div>
        ) : files.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-text-muted">
            <svg width="48" height="48" viewBox="0 0 28 28" fill="none">
              <defs>
                <linearGradient id="emptyFiles" x1="0" y1="0" x2="28" y2="28" gradientUnits="userSpaceOnUse">
                  <stop stopColor="#f5bc7a" stopOpacity="0.3" />
                  <stop offset="1" stopColor="#f8cfa0" stopOpacity="0.2" />
                </linearGradient>
              </defs>
              <path d="M2 5 V12 A1 1 0 0 0 3 13 H13 A1 1 0 0 0 14 12 V6 A1 1 0 0 0 13 5 H8 L6.5 3 H3 A1 1 0 0 0 2 4 Z" fill="url(#emptyFiles)" />
            </svg>
            <p className="text-sm text-text-secondary font-serif italic">Пока нет файлов</p>
          </div>
        ) : (
          <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(230px, 1fr))' }}>
            {files.map((f) => <FileCard key={f.id} f={f} />)}
            <UploadZone />
          </div>
        )}
      </div>
    </ScreenShell>
  );
}

function guessKind(name: string): FileItem['kind'] {
  const lower = name.toLowerCase();
  if (lower.endsWith('.pdf')) return 'pdf';
  if (lower.endsWith('.docx') || lower.endsWith('.doc')) return 'doc';
  if (lower.endsWith('.xlsx') || lower.endsWith('.csv')) return 'sheet';
  if (lower.endsWith('.png') || lower.endsWith('.jpg') || lower.endsWith('.jpeg') || lower.endsWith('.gif')) return 'img';
  if (lower.endsWith('.mp3') || lower.endsWith('.m4a') || lower.endsWith('.wav')) return 'audio';
  if (lower.endsWith('.zip') || lower.endsWith('.tar') || lower.endsWith('.gz')) return 'zip';
  return 'doc';
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} КБ`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
}
