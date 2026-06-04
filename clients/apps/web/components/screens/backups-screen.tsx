'use client';

import React, { useState, useEffect, useCallback } from 'react';
import type { MiraClient } from '@mira/shared';
import { SectionHeader, PrimaryBtn, ScreenShell } from './screen-primitives';

const BackupIco = {
  restore: (c = 'currentColor') => <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M3 8 A5 5 0 1 1 4.5 11.5 M3 12 V8.5 H6.5" stroke={c} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>,
  download: (c = 'currentColor') => <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M8 2 V10 M5 7.5 L8 10.5 L11 7.5 M3.5 13 H12.5" stroke={c} strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round"/></svg>,
  trash: (c = 'currentColor') => <svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M3 4 H13 M5 4 V13 A1 1 0 0 0 6 14 H10 A1 1 0 0 0 11 13 V4 M6.5 4 V2.5 H9.5 V4" stroke={c} strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round"/></svg>,
};

interface Backup {
  when: string;
  size: string;
  type: 'авто' | 'вручную';
  facts: number;
  notes: number;
  latest?: boolean;
}

function _fmtBackupSize(bytes: number): string {
  if (!bytes) return '—';
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} КБ`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} МБ`;
  return `${(bytes / 1024 / 1024 / 1024).toFixed(2)} ГБ`;
}

function _mapBackup(b: any): Backup {
  return {
    when: b.created_at || '',
    size: _fmtBackupSize(b.size || 0),
    type: b.type === 'manual' ? 'вручную' : 'авто',
    facts: b.fact_count || 0,
    notes: b.note_count || 0,
    latest: !!b.is_latest,
  };
}

function BackupRow({ b }: { b: Backup }) {
  return (
    <div
      className="flex items-center gap-3.5 px-4 py-3"
      style={{ borderBottom: '1px solid rgba(244,234,214,0.06)', background: b.latest ? 'rgba(245,188,122,0.04)' : 'transparent' }}
    >
      <div
        className="w-9 h-9 rounded-lg shrink-0 flex items-center justify-center"
        style={{
          background: b.latest ? 'rgba(245,188,122,0.10)' : 'rgba(255,255,255,0.03)',
          border: `1px solid ${b.latest ? 'rgba(245,188,122,0.30)' : 'rgba(244,234,214,0.10)'}`,
          color: b.latest ? '#f5bc7a' : 'rgba(244,234,214,0.36)',
        }}
      >
        <svg width="18" height="18" viewBox="0 0 16 16" fill="none"><path d="M2.5 5 L8 2.5 L13.5 5 V11 L8 13.5 L2.5 11 Z M2.5 5 L8 7.5 L13.5 5 M8 7.5 V13.5" stroke="currentColor" strokeWidth="1.1" strokeLinejoin="round"/></svg>
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-medium" style={{ color: '#f4ead6' }}>{b.when}</span>
          {b.latest && (
            <span
              className="text-[9.5px] px-1.5 py-0.5 rounded-pill tracking-wide"
              style={{ background: 'rgba(245,188,122,0.10)', border: '1px solid rgba(245,188,122,0.30)', color: '#f5bc7a' }}
            >актуальная</span>
          )}
          <span
            className="text-[9.5px] tracking-wide"
            style={{ color: b.type === 'авто' ? '#8dd0a7' : '#b9a3ff' }}
          >{b.type}</span>
        </div>
        <div className="text-[11px] text-text-muted mt-0.5 font-mono">{b.size} · {b.facts} фактов · {b.notes} заметки</div>
      </div>
      <div className="flex gap-1.5 shrink-0">
        <button className="w-[30px] h-[30px] rounded-md inline-flex items-center justify-center" style={{ border: '1px solid rgba(245,188,122,0.30)', color: '#f5bc7a' }}>{BackupIco.restore('#f5bc7a')}</button>
        <button className="w-[30px] h-[30px] rounded-md inline-flex items-center justify-center" style={{ border: '1px solid rgba(244,234,214,0.10)', color: 'rgba(244,234,214,0.36)' }}>{BackupIco.download()}</button>
        <button className="w-[30px] h-[30px] rounded-md inline-flex items-center justify-center" style={{ border: '1px solid rgba(244,234,214,0.10)', color: 'rgba(244,234,214,0.36)' }}>{BackupIco.trash()}</button>
      </div>
    </div>
  );
}

export function BackupsScreen({ client }: { client: MiraClient | null }) {
  const [backups, setBackups] = useState<Backup[]>([]);

  const load = useCallback(async () => {
    if (!client) return;
    try {
      const msg = await client.sendCommandAwait('backups_data', ['backups_data'], 12000);
      if ('backups' in msg && Array.isArray((msg as any).backups)) {
        setBackups((msg as any).backups.map(_mapBackup));
      }
    } catch {
      // оставляем пусто
    }
  }, [client]);

  useEffect(() => { load(); }, [load]);

  return (
    <ScreenShell>
      <SectionHeader
        title="Резервные копии"
        subtitle="снимки памяти Миры · можно вернуться к любому моменту"
        actions={
          <PrimaryBtn gold>
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" className="inline mr-1"><path d="M7 2 V12 M2 7 H12" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>
            создать копию
          </PrimaryBtn>
        }
      />

      <div className="flex-1 overflow-y-auto mira-scroll" style={{ padding: '24px 32px 40px' }}>
        {/* Config + storage */}
        <div className="grid grid-cols-2 gap-4 mb-6">
          <div className="p-5 rounded-xl" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(244,234,214,0.10)' }}>
            <div className="flex items-center gap-2.5 mb-3.5">
              <span className="uppercase text-[10px] font-semibold tracking-[0.18em] text-gold">авто-копирование</span>
              <div className="flex-1" />
              <div
                className="w-[38px] h-[21px] rounded-pill p-0.5 flex items-center justify-end"
                style={{ background: 'rgba(245,188,122,0.10)', border: '1px solid rgba(245,188,122,0.30)' }}
              >
                <div className="w-[15px] h-[15px] rounded-full bg-gold" />
              </div>
            </div>
            <div className="flex flex-col gap-2">
              {[
                { l: 'расписание', v: 'каждый день · 03:00' },
                { l: 'хранить копий', v: 'последние 7' },
                { l: 'куда', v: 'Google Drive' },
              ].map((r, i) => (
                <div key={i} className="flex items-center">
                  <span className="text-xs text-text-dim">{r.l}</span>
                  <div className="flex-1" />
                  <span className="text-xs text-text-primary font-mono">{r.v}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="p-5 rounded-xl" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(244,234,214,0.10)' }}>
            <div className="uppercase text-[10px] font-semibold tracking-[0.18em] text-gold mb-3.5">хранилище</div>
            <div className="flex items-baseline gap-1.5 mb-3">
              <span className="text-[26px] font-mono leading-none" style={{ color: '#f4ead6' }}>7.0</span>
              <span className="text-[13px] text-text-muted">ГБ из 15 ГБ Drive</span>
            </div>
            <div className="h-2 rounded-pill overflow-hidden flex" style={{ background: 'rgba(255,255,255,0.05)' }}>
              <div className="h-full" style={{ width: '32%', background: '#f5bc7a' }} />
              <div className="h-full" style={{ width: '15%', background: '#b9a3ff', opacity: 0.6 }} />
            </div>
            <div className="flex gap-4 mt-3">
              <span className="inline-flex items-center gap-1.5 text-[10.5px] text-text-muted">
                <span className="w-[7px] h-[7px] rounded-sm bg-gold" /> копии Миры · 4.8 ГБ
              </span>
              <span className="inline-flex items-center gap-1.5 text-[10.5px] text-text-muted">
                <span className="w-[7px] h-[7px] rounded-sm bg-mystic/60" /> файлы · 2.2 ГБ
              </span>
            </div>
          </div>
        </div>

        {/* Backups list */}
        <div className="rounded-xl overflow-hidden" style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(244,234,214,0.10)' }}>
          <div className="px-4 py-3.5 flex items-center" style={{ borderBottom: '1px solid rgba(244,234,214,0.06)' }}>
            <span className="uppercase text-[10px] font-semibold tracking-[0.18em] text-gold">история копий</span>
            <span className="ml-auto text-[11px] text-text-muted font-mono">{backups.length} снимков</span>
          </div>
          {backups.map((b, i) => <BackupRow key={i} b={b} />)}
        </div>

        {/* Restore warning */}
        <div
          className="flex items-start gap-3 mt-5 px-4 py-3.5 rounded-[10px]"
          style={{
            background: 'rgba(232,138,138,0.05)',
            border: '1px solid rgba(232,138,138,0.20)',
            borderLeft: '3px solid #e88a8a',
          }}
        >
          <span className="text-rose mt-0.5">{BackupIco.restore('#e88a8a')}</span>
          <div>
            <div className="text-[12.5px] font-medium mb-0.5" style={{ color: '#f4ead6' }}>Восстановление заменит текущую память</div>
            <div className="text-[11.5px] text-text-muted leading-relaxed">
              Всё, что Мира узнала после выбранной копии, будет потеряно. Перед восстановлением я создам копию текущего состояния.
            </div>
          </div>
        </div>
      </div>
    </ScreenShell>
  );
}
