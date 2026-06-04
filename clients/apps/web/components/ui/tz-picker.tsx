'use client';

import React, { useState } from 'react';
import { ChevronDown, X } from 'lucide-react';

const TIMEZONES = [
  { value: 'Europe/Moscow', label: 'Москва · GMT+3' },
  { value: 'Europe/Kaliningrad', label: 'Калининград · GMT+2' },
  { value: 'Europe/Samara', label: 'Самара · GMT+4' },
  { value: 'Asia/Yekaterinburg', label: 'Екатеринбург · GMT+5' },
  { value: 'Asia/Omsk', label: 'Омск · GMT+6' },
  { value: 'Asia/Krasnoyarsk', label: 'Красноярск · GMT+7' },
  { value: 'Asia/Irkutsk', label: 'Иркутск · GMT+8' },
  { value: 'Asia/Yakutsk', label: 'Якутск · GMT+9' },
  { value: 'Asia/Vladivostok', label: 'Владивосток · GMT+10' },
  { value: 'Asia/Magadan', label: 'Магадан · GMT+11' },
  { value: 'Asia/Kamchatka', label: 'Камчатка · GMT+12' },
  { value: 'Europe/London', label: 'Лондон · GMT+0/+1' },
  { value: 'Europe/Paris', label: 'Париж · GMT+1/+2' },
  { value: 'Europe/Berlin', label: 'Берлин · GMT+1/+2' },
  { value: 'Europe/Warsaw', label: 'Варшава · GMT+1/+2' },
  { value: 'Europe/Athens', label: 'Афины · GMT+2/+3' },
  { value: 'Europe/Istanbul', label: 'Стамбул · GMT+3' },
  { value: 'Asia/Dubai', label: 'Дубай · GMT+4' },
  { value: 'Asia/Tbilisi', label: 'Тбилиси · GMT+4' },
  { value: 'Asia/Tashkent', label: 'Ташкент · GMT+5' },
  { value: 'Asia/Almaty', label: 'Алматы · GMT+5' },
  { value: 'Asia/Bangkok', label: 'Бангкок · GMT+7' },
  { value: 'Asia/Singapore', label: 'Сингапур · GMT+8' },
  { value: 'Asia/Shanghai', label: 'Шанхай · GMT+8' },
  { value: 'Asia/Tokyo', label: 'Токио · GMT+9' },
  { value: 'Australia/Sydney', label: 'Сидней · GMT+10/+11' },
  { value: 'Pacific/Auckland', label: 'Окленд · GMT+12/+13' },
  { value: 'America/New_York', label: 'Нью-Йорк · GMT-5/-4' },
  { value: 'America/Chicago', label: 'Чикаго · GMT-6/-5' },
  { value: 'America/Denver', label: 'Денвер · GMT-7/-6' },
  { value: 'America/Los_Angeles', label: 'Лос-Анджелес · GMT-8/-7' },
  { value: 'America/Toronto', label: 'Торонто · GMT-5/-4' },
  { value: 'America/Vancouver', label: 'Ванкувер · GMT-8/-7' },
  { value: 'America/Sao_Paulo', label: 'Сан-Паулу · GMT-3' },
  { value: 'America/Buenos_Aires', label: 'Буэнос-Айрес · GMT-3' },
];

export function tzLabel(value: string): string {
  const t = TIMEZONES.find((x) => x.value === value);
  return t?.label || value;
}

interface TzPickerProps {
  value: string;
  onChange: (value: string) => void;
}

export function TzPicker({ value, onChange }: TzPickerProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');

  const filtered = search.trim()
    ? TIMEZONES.filter((t) => t.label.toLowerCase().includes(search.toLowerCase()) || t.value.toLowerCase().includes(search.toLowerCase()))
    : TIMEZONES;

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center bg-bg-base border border-border-subtle rounded-button px-3 py-2 text-sm text-left"
      >
        <span className={value ? 'text-text-primary' : 'text-text-faint'}>
          {value ? tzLabel(value) : 'Часовой пояс — выбрать из списка'}
        </span>
        <ChevronDown size={15} className="ml-auto text-text-muted" />
      </button>
      {open && (
        <div className="absolute z-10 left-0 right-0 mt-1 max-h-56 overflow-y-auto rounded-card bg-bg-overlay border border-border-subtle shadow-elevated">
          <div className="sticky top-0 bg-bg-overlay border-b border-border-subtle p-2">
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Поиск..."
              className="w-full bg-bg-base border border-border-subtle rounded-button px-3 py-1.5 text-sm text-text-primary placeholder:text-text-faint outline-none"
              autoFocus
            />
          </div>
          {filtered.map((t) => (
            <button
              key={t.value}
              onClick={() => { onChange(t.value); setOpen(false); setSearch(''); }}
              className={`w-full text-left px-3 py-2 text-sm hover:bg-gold/5 ${value === t.value ? 'text-gold' : 'text-text-primary'}`}
            >
              {t.label}
            </button>
          ))}
          {filtered.length === 0 && (
            <div className="px-3 py-2 text-sm text-text-muted">Не найдено</div>
          )}
        </div>
      )}
    </div>
  );
}
