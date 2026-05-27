import * as React from 'react';

// Фирменные Aurora-иконки (viewBox 16, stroke 1.1, currentColor).
// Цвет наследуется от CSS color родителя (style.color).

// chat
import IcChat from './chat/chat.svg';
import IcClear from './chat/clear.svg';
import IcForget from './chat/forget.svg';
import IcHelp from './chat/help.svg';
import IcProfile from './chat/profile.svg';
import IcStop from './chat/stop.svg';
import IcTz from './chat/tz.svg';
// files
import IcFolder from './files/folder.svg';
import IcMyfiles from './files/myfiles.svg';
// google
import IcAutoup from './google/autoup.svg';
import IcCal from './google/cal.svg';
import IcCalNew from './google/calNew.svg';
import IcCloud from './google/cloud.svg';
import IcDriveDown from './google/driveDown.svg';
import IcDriveLink from './google/driveLink.svg';
import IcDriveList from './google/driveList.svg';
import IcDriveStatus from './google/driveStatus.svg';
import IcDriveUnlink from './google/driveUnlink.svg';
import IcSheetNew from './google/sheetNew.svg';
import IcSheetRead from './google/sheetRead.svg';
// reminders
import IcBell from './reminders/bell.svg';
import IcRemList from './reminders/remList.svg';
import IcRemNew from './reminders/remNew.svg';
// tasks
import IcTask from './tasks/task.svg';
import IcTaskDefer from './tasks/taskDefer.svg';
import IcTaskList from './tasks/taskList.svg';
// tools
import IcGenImg from './tools/genImg.svg';
import IcTool from './tools/tool.svg';
// owner
import IcBackup from './owner/backup.svg';
import IcBlacklist from './owner/blacklist.svg';
import IcChild from './owner/child.svg';
import IcEvolve from './owner/evolve.svg';
import IcLock from './owner/lock.svg';
import IcMetrics from './owner/metrics.svg';
import IcRename from './owner/rename.svg';
import IcReview from './owner/review.svg';
import IcRituals from './owner/rituals.svg';
import IcUsers from './owner/users.svg';
// misc
import IcBack from './misc/back.svg';
import IcDiary from './misc/diary.svg';
import IcFiles from './misc/files.svg';
import IcMemory from './misc/memory.svg';
import IcMenu from './misc/menu.svg';
import IcMic from './misc/mic.svg';
import IcMoon from './misc/moon.svg';
import IcMore from './misc/more.svg';
import IcNotes from './misc/notes.svg';
import IcPaperclip from './misc/paperclip.svg';
import IcPersonality from './misc/personality.svg';
import IcPlus from './misc/plus.svg';
import IcSearch from './misc/search.svg';
import IcSend from './misc/send.svg';
import IcSkills from './misc/skills.svg';

type SvgComp = React.FC<React.SVGProps<SVGSVGElement>>;

const MAP: Record<string, SvgComp> = {
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

export function MiraIcon({ name, size = 16, color }: { name: string; size?: number; color?: string }) {
  const Cmp = MAP[name];
  if (!Cmp) return null;
  return <Cmp width={size} height={size} style={color ? { color } : undefined} />;
}
