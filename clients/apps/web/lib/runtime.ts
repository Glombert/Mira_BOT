export const IS_TAURI =
  typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window;
