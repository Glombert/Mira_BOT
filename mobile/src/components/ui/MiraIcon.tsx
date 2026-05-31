import React from 'react';
import { SvgProps } from 'react-native-svg';

// Фирменные Aurora-иконки (тонкая линия 1.1, viewBox 16, currentColor).
// Источник: дизайн-пакет icons/. Цвет задаётся через prop `color`
// (react-native-svg прокидывает его в currentColor).

// chat
import IcChat from '../../assets/icons/chat/chat.svg';
import IcClear from '../../assets/icons/chat/clear.svg';
import IcForget from '../../assets/icons/chat/forget.svg';
import IcHelp from '../../assets/icons/chat/help.svg';
import IcProfile from '../../assets/icons/chat/profile.svg';
import IcStop from '../../assets/icons/chat/stop.svg';
import IcTz from '../../assets/icons/chat/tz.svg';
// files
import IcFolder from '../../assets/icons/files/folder.svg';
import IcMyfiles from '../../assets/icons/files/myfiles.svg';
// google
import IcAutoup from '../../assets/icons/google/autoup.svg';
import IcCal from '../../assets/icons/google/cal.svg';
import IcCalNew from '../../assets/icons/google/calNew.svg';
import IcCloud from '../../assets/icons/google/cloud.svg';
import IcDriveDown from '../../assets/icons/google/driveDown.svg';
import IcDriveLink from '../../assets/icons/google/driveLink.svg';
import IcDriveList from '../../assets/icons/google/driveList.svg';
import IcDriveStatus from '../../assets/icons/google/driveStatus.svg';
import IcDriveUnlink from '../../assets/icons/google/driveUnlink.svg';
import IcSheetNew from '../../assets/icons/google/sheetNew.svg';
import IcSheetRead from '../../assets/icons/google/sheetRead.svg';
// reminders
import IcBell from '../../assets/icons/reminders/bell.svg';
import IcRemList from '../../assets/icons/reminders/remList.svg';
import IcRemNew from '../../assets/icons/reminders/remNew.svg';
// tasks
import IcTask from '../../assets/icons/tasks/task.svg';
import IcTaskDefer from '../../assets/icons/tasks/taskDefer.svg';
import IcTaskList from '../../assets/icons/tasks/taskList.svg';
// tools
import IcGenImg from '../../assets/icons/tools/genImg.svg';
import IcTool from '../../assets/icons/tools/tool.svg';
// owner
import IcBackup from '../../assets/icons/owner/backup.svg';
import IcBlacklist from '../../assets/icons/owner/blacklist.svg';
import IcChild from '../../assets/icons/owner/child.svg';
import IcEvolve from '../../assets/icons/owner/evolve.svg';
import IcLock from '../../assets/icons/owner/lock.svg';
import IcMetrics from '../../assets/icons/owner/metrics.svg';
import IcRename from '../../assets/icons/owner/rename.svg';
import IcReview from '../../assets/icons/owner/review.svg';
import IcRituals from '../../assets/icons/owner/rituals.svg';
import IcUsers from '../../assets/icons/owner/users.svg';
// misc
import IcBack from '../../assets/icons/misc/back.svg';
import IcDiary from '../../assets/icons/misc/diary.svg';
import IcFiles from '../../assets/icons/misc/files.svg';
import IcMemory from '../../assets/icons/misc/memory.svg';
import IcMenu from '../../assets/icons/misc/menu.svg';
import IcMic from '../../assets/icons/misc/mic.svg';
import IcMoon from '../../assets/icons/misc/moon.svg';
import IcMore from '../../assets/icons/misc/more.svg';
import IcNotes from '../../assets/icons/misc/notes.svg';
import IcPaperclip from '../../assets/icons/misc/paperclip.svg';
import IcPersonality from '../../assets/icons/misc/personality.svg';
import IcPlus from '../../assets/icons/misc/plus.svg';
import IcSearch from '../../assets/icons/misc/search.svg';
import IcSend from '../../assets/icons/misc/send.svg';
import IcSkills from '../../assets/icons/misc/skills.svg';

const MAP: Record<string, React.FC<SvgProps>> = {
  chat: IcChat, clear: IcClear, forget: IcForget, help: IcHelp, profile: IcProfile, stop: IcStop, tz: IcTz,
  folder: IcFolder, myfiles: IcMyfiles,
  autoup: IcAutoup, cal: IcCal, calNew: IcCalNew, cloud: IcCloud, driveDown: IcDriveDown,
  driveLink: IcDriveLink, driveList: IcDriveList, driveStatus: IcDriveStatus, driveUnlink: IcDriveUnlink,
  sheetNew: IcSheetNew, sheetRead: IcSheetRead,
  bell: IcBell, remList: IcRemList, remNew: IcRemNew,
  task: IcTask, taskDefer: IcTaskDefer, taskList: IcTaskList,
  genImg: IcGenImg, tool: IcTool,
  backup: IcBackup, blacklist: IcBlacklist, child: IcChild, evolve: IcEvolve, lock: IcLock,
  metrics: IcMetrics, rename: IcRename, review: IcReview, rituals: IcRituals, users: IcUsers,
  back: IcBack, diary: IcDiary, files: IcFiles, memory: IcMemory, menu: IcMenu, mic: IcMic,
  moon: IcMoon, more: IcMore, notes: IcNotes, paperclip: IcPaperclip, personality: IcPersonality,
  plus: IcPlus, search: IcSearch, send: IcSend, skills: IcSkills,
};

export type MiraIconName = keyof typeof MAP | string;

export function MiraIcon({
  name,
  size = 18,
  color = '#f4ead6',
}: {
  name: MiraIconName;
  size?: number;
  color?: string;
}) {
  const Cmp = MAP[name];
  if (!Cmp) return null;
  return <Cmp width={size} height={size} color={color} />;
}
