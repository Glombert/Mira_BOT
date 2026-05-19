import {
  Trash2,
  User,
  Folder,
  Eraser,
  Cloud,
  Calendar,
  FileSpreadsheet,
  Bell,
  type LucideIcon,
} from 'lucide-react';

export interface CommandDef {
  id: string;
  label: string;
  description: string;
  cmd: string;
  icon: LucideIcon;
  hasArgs: boolean;
  destructive?: boolean;
  args?: CommandArg[];
}

export interface CommandArg {
  name: string;
  label: string;
  type: 'text' | 'number' | 'datetime-local' | 'textarea';
  placeholder?: string;
  optional?: boolean;
}

export const COMMANDS: CommandDef[] = [
  { id: 'clear', label: 'Очистить историю', description: 'Удалить всю переписку', cmd: 'clear', icon: Trash2, hasArgs: false, destructive: true },
  { id: 'whoami', label: 'Профиль', description: 'Кто я', cmd: 'whoami', icon: User, hasArgs: false },
  { id: 'files', label: 'Файлы', description: 'Список файлов', cmd: 'files', icon: Folder, hasArgs: false },
  { id: 'forget', label: 'Забыть меня', description: 'Сбросить профиль и историю', cmd: 'forget', icon: Eraser, hasArgs: false, destructive: true },
  { id: 'gdrive_login', label: 'Google Drive', description: 'Привязать Google Drive', cmd: 'gdrive_login', icon: Cloud, hasArgs: false },
  { id: 'gdrive_status', label: 'Статус Drive', description: 'Статус Google Drive', cmd: 'gdrive_status', icon: Cloud, hasArgs: false },
  {
    id: 'gdrive_list',
    label: 'Список на Drive',
    description: 'Посмотреть файлы на Google Drive',
    cmd: 'gdrive_list',
    icon: Cloud,
    hasArgs: true,
    args: [{ name: 'folder', label: 'Папка', type: 'text', placeholder: 'root (опционально)', optional: true }],
  },
  {
    id: 'gdrive_get',
    label: 'Скачать с Drive',
    description: 'Скачать файл по ID',
    cmd: 'gdrive_get',
    icon: Cloud,
    hasArgs: true,
    args: [{ name: 'id', label: 'ID файла', type: 'text', placeholder: '1A2B3C4D5E' }],
  },
  {
    id: 'gcal',
    label: 'Календарь',
    description: 'Ближайшие события',
    cmd: 'gcal',
    icon: Calendar,
    hasArgs: true,
    args: [{ name: 'n', label: 'Количество', type: 'number', placeholder: '10', optional: true }],
  },
  {
    id: 'gcal_create',
    label: 'Создать событие',
    description: 'Добавить событие в календарь',
    cmd: 'gcal_create',
    icon: Calendar,
    hasArgs: true,
    args: [{ name: 'text', label: 'Описание', type: 'textarea', placeholder: 'Встреча с Колей завтра в 15:00' }],
  },
  {
    id: 'gsheet',
    label: 'Таблица',
    description: 'Прочитать Google Таблицу',
    cmd: 'gsheet',
    icon: FileSpreadsheet,
    hasArgs: true,
    args: [
      { name: 'id', label: 'ID таблицы', type: 'text', placeholder: '1A2B3C4D' },
      { name: 'range', label: 'Диапазон', type: 'text', placeholder: 'A1:Z100 (опционально)', optional: true },
    ],
  },
  {
    id: 'gsheet_create',
    label: 'Создать таблицу',
    description: 'Новая Google Таблица',
    cmd: 'gsheet_create',
    icon: FileSpreadsheet,
    hasArgs: true,
    args: [{ name: 'title', label: 'Название', type: 'text', placeholder: 'Новая таблица', optional: true }],
  },
  {
    id: 'remind',
    label: 'Напоминание',
    description: 'Создать напоминание',
    cmd: 'remind',
    icon: Bell,
    hasArgs: true,
    args: [
      { name: 'datetime', label: 'Когда', type: 'datetime-local', placeholder: '' },
      { name: 'text', label: 'Текст', type: 'textarea', placeholder: 'Утренний кофе' },
    ],
  },
  { id: 'reminders', label: 'Мои напоминания', description: 'Список активных', cmd: 'reminders', icon: Bell, hasArgs: false },
  {
    id: 'remind_cancel',
    label: 'Отменить напоминание',
    description: 'Удалить по ID',
    cmd: 'remind_cancel',
    icon: Bell,
    hasArgs: true,
    args: [{ name: 'id', label: 'ID', type: 'text', placeholder: 'a3f7b2c1' }],
  },
];
