import { invoke } from '@tauri-apps/api/core';
import type { SessionStorage } from '@mira/shared';

export const tauriSessionStorage: SessionStorage = {
  async get() {
    return await invoke<string | null>('session_get');
  },
  async set(token: string) {
    await invoke('session_set', { token });
  },
  async clear() {
    await invoke('session_clear');
  },
};
