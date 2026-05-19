import type { SessionStorage } from '@mira/shared';

const KEY = 'mira_session';

export const webSessionStorage: SessionStorage = {
  async get() {
    return typeof window !== 'undefined' ? localStorage.getItem(KEY) : null;
  },
  async set(token: string) {
    if (typeof window !== 'undefined') localStorage.setItem(KEY, token);
  },
  async clear() {
    if (typeof window !== 'undefined') localStorage.removeItem(KEY);
  },
};
