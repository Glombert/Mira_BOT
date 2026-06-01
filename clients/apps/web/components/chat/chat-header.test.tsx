import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ChatHeader } from './chat-header';

const base = {
  userName: 'Andrey',
  onClear: () => {},
  onWhoami: () => {},
  onOpenPalette: () => {},
  onOpenReminders: () => {},
  onOpenDrive: () => {},
};

describe('ChatHeader — статус соединения', () => {
  it('online: «на связи», статус не кнопка реконнекта', () => {
    render(<ChatHeader {...base} connectionStatus="online" onReconnect={() => {}} />);
    expect(screen.getByText(/на связи/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: /Переподключиться/ })).toBeNull();
  });

  it('offline: статус — кнопка, клик вызывает onReconnect', () => {
    const onReconnect = vi.fn();
    render(<ChatHeader {...base} connectionStatus="offline" onReconnect={onReconnect} />);
    const btn = screen.getByRole('button', { name: /Переподключиться/ });
    fireEvent.click(btn);
    expect(onReconnect).toHaveBeenCalledTimes(1);
  });

  it('reconnecting: кнопка отключена', () => {
    render(<ChatHeader {...base} connectionStatus="reconnecting" onReconnect={() => {}} />);
    const btn = screen.getByRole('button', { name: /Переподключиться/ }) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
  });
});
