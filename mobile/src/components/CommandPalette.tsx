import React, { useState, useMemo } from 'react';
import {
  Modal,
  View,
  Text,
  TouchableOpacity,
  TextInput,
  StyleSheet,
  ScrollView,
} from 'react-native';

interface Command {
  cmd: string;
  label: string;
  desc: string;
  owner?: boolean;
}

const COMMANDS: Command[] = [
  { cmd: 'clear', label: '🗑 Очистить историю', desc: 'Удалить все сообщения' },
  { cmd: 'whoami', label: '👤 Кто я', desc: 'Профиль и статус' },
  { cmd: 'files', label: '📁 Файлы', desc: 'Список загруженных файлов' },
  { cmd: 'reminders', label: '🔔 Напоминания', desc: 'Показать список' },
  { cmd: 'gdrive_status', label: '☁️ Drive статус', desc: 'Статус Google Drive' },
  { cmd: 'gdrive_list', label: '☁️ Drive файлы', desc: 'Список файлов на Drive' },
  { cmd: 'gcal', label: '📅 Календарь', desc: 'Ближайшие события' },
  { cmd: 'help', label: '❓ Помощь', desc: 'Список команд' },
  // Owner-only (сервер отбросит для не-владельца с понятным сообщением).
  // Деструктивные (/evolve, /rollback, /release, /restart) намеренно НЕ
  // выведены сюда — они только в Telegram.
  { cmd: 'stats',           label: '📊 Метрики LLM',     desc: 'Статистика использования (24ч)', owner: true },
  { cmd: 'users',           label: '👥 Пользователи',    desc: 'Список пользователей',           owner: true },
  { cmd: 'versions',        label: '📦 Резервные копии', desc: 'Список бэкапов agent.py',        owner: true },
  { cmd: 'evolution_count', label: '🧬 Счётчик /evolve', desc: 'Сколько раз правил себя',        owner: true },
  { cmd: 'blacklist',       label: '🚫 Чёрный список',   desc: 'Заблокированные пользователи',   owner: true },
];

interface Props {
  visible: boolean;
  onClose: () => void;
  onRun: (cmd: string) => void;
}

export function CommandPalette({ visible, onClose, onRun }: Props) {
  const [query, setQuery] = useState('');

  const filtered = useMemo(() => {
    const q = query.toLowerCase();
    return COMMANDS.filter(
      (c) => c.label.toLowerCase().includes(q) || c.desc.toLowerCase().includes(q)
    );
  }, [query]);

  const handlePress = (cmd: string) => {
    onRun(cmd);
    setQuery('');
    onClose();
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={styles.card}>
          <TextInput
            style={styles.input}
            value={query}
            onChangeText={setQuery}
            placeholder="Поиск команд..."
            placeholderTextColor="#555"
            autoFocus
          />
          <ScrollView showsVerticalScrollIndicator={false} style={{ maxHeight: 380 }}>
            {filtered.filter((c) => !c.owner).map((item) => (
              <TouchableOpacity
                key={item.cmd}
                style={styles.item}
                onPress={() => handlePress(item.cmd)}
              >
                <Text style={styles.itemLabel}>{item.label}</Text>
                <Text style={styles.itemDesc}>{item.desc}</Text>
              </TouchableOpacity>
            ))}
            {filtered.some((c) => c.owner) && (
              <Text style={styles.sectionHeader}>🔐 Только владелец</Text>
            )}
            {filtered.filter((c) => c.owner).map((item) => (
              <TouchableOpacity
                key={item.cmd}
                style={styles.item}
                onPress={() => handlePress(item.cmd)}
              >
                <Text style={styles.itemLabel}>{item.label}</Text>
                <Text style={styles.itemDesc}>{item.desc}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: '#000000aa',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  card: {
    width: '100%',
    backgroundColor: '#12122a',
    borderRadius: 20,
    borderWidth: 1,
    borderColor: '#2a2a4a',
    padding: 16,
  },
  input: {
    backgroundColor: '#1a1a3e',
    borderRadius: 12,
    padding: 12,
    color: '#e0e0f0',
    fontSize: 15,
    borderWidth: 1,
    borderColor: '#2a2a4a',
    marginBottom: 8,
  },
  item: {
    paddingVertical: 10,
    paddingHorizontal: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#1a1a3e',
  },
  itemLabel: { color: '#e0e0f0', fontSize: 15, fontWeight: '600' },
  itemDesc: { color: '#666688', fontSize: 12, marginTop: 2 },
  sectionHeader: {
    color: '#FF8C42',
    fontSize: 12,
    fontWeight: '600',
    marginTop: 12,
    marginBottom: 4,
    paddingHorizontal: 8,
  },
});
