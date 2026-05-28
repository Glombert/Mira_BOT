// Курируемый список часовых поясов для picker (IANA + человекочитаемая подпись).
export interface TzOption { value: string; label: string }

export const TIMEZONES: TzOption[] = [
  { value: 'Europe/Kaliningrad', label: 'Калининград · GMT+2' },
  { value: 'Europe/Moscow', label: 'Москва · GMT+3' },
  { value: 'Europe/Samara', label: 'Самара · GMT+4' },
  { value: 'Asia/Yekaterinburg', label: 'Екатеринбург · GMT+5' },
  { value: 'Asia/Omsk', label: 'Омск · GMT+6' },
  { value: 'Asia/Krasnoyarsk', label: 'Красноярск · GMT+7' },
  { value: 'Asia/Irkutsk', label: 'Иркутск · GMT+8' },
  { value: 'Asia/Yakutsk', label: 'Якутск · GMT+9' },
  { value: 'Asia/Vladivostok', label: 'Владивосток · GMT+10' },
  { value: 'Asia/Magadan', label: 'Магадан · GMT+11' },
  { value: 'Asia/Kamchatka', label: 'Камчатка · GMT+12' },
  { value: 'Europe/Minsk', label: 'Минск · GMT+3' },
  { value: 'Europe/Kyiv', label: 'Киев · GMT+2' },
  { value: 'Asia/Almaty', label: 'Алматы · GMT+5' },
  { value: 'Asia/Tashkent', label: 'Ташкент · GMT+5' },
  { value: 'Asia/Tbilisi', label: 'Тбилиси · GMT+4' },
  { value: 'Asia/Yerevan', label: 'Ереван · GMT+4' },
  { value: 'Asia/Baku', label: 'Баку · GMT+4' },
  { value: 'Europe/Berlin', label: 'Берлин · GMT+1' },
  { value: 'Europe/London', label: 'Лондон · GMT+0' },
  { value: 'UTC', label: 'UTC · GMT+0' },
  { value: 'America/New_York', label: 'Нью-Йорк · GMT−5' },
  { value: 'America/Los_Angeles', label: 'Лос-Анджелес · GMT−8' },
];

export function tzLabel(value: string): string {
  return TIMEZONES.find((t) => t.value === value)?.label || value;
}
