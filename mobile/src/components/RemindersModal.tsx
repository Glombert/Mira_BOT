import React, { useState, useEffect, useCallback } from 'react';
import {
  Modal,
  View,
  Text,
  TouchableOpacity,
  TextInput,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
} from 'react-native';
import type { MiraClient } from '../api/mira-client';

interface Props {
  visible: boolean;
  onClose: () => void;
  client: MiraClient | null;
}

export function RemindersModal({ visible, onClose, client }: Props) {
  const [datetime, setDatetime] = useState('');
  const [text, setText] = useState('');
  const [cancelId, setCancelId] = useState('');
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (visible) {
      setDatetime('');
      setText('');
      setCancelId('');
      setResult(null);
      setLoading(false);
    }
  }, [visible]);

  const run = useCallback(async (cmd: string) => {
    if (!client) return;
    setLoading(true);
    setResult(null);
    try {
      const msg = await client.sendCommandAwait(cmd, ['system'], 15000);
      setResult(msg.content);
    } catch {
      setResult('Ошибка: нет ответа от сервера');
    } finally {
      setLoading(false);
    }
  }, [client]);

  const handleCreate = useCallback(() => {
    if (datetime && text) {
      const dt = datetime.includes('T') && datetime.split('T')[1]?.length === 5
        ? `${datetime}:00`
        : datetime;
      run(`remind ${dt} ${text}`);
    }
  }, [datetime, text, run]);

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={styles.card}>
          <View style={styles.header}>
            <Text style={styles.title}>🔔 Напоминания</Text>
            <TouchableOpacity onPress={onClose}>
              <Text style={styles.close}>✕</Text>
            </TouchableOpacity>
          </View>

          <ScrollView showsVerticalScrollIndicator={false}>
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Создать</Text>
              <Text style={styles.label}>Когда</Text>
              <TextInput
                style={styles.input}
                value={datetime}
                onChangeText={setDatetime}
                placeholder="2026-05-20T14:00"
                placeholderTextColor="#555"
              />
              <Text style={styles.label}>Текст</Text>
              <TextInput
                style={[styles.input, { height: 60 }]}
                value={text}
                onChangeText={setText}
                placeholder="Утренний кофе"
                placeholderTextColor="#555"
                multiline
              />
              <TouchableOpacity style={styles.primaryBtn} onPress={handleCreate}>
                <Text style={styles.primaryText}>➕ Создать</Text>
              </TouchableOpacity>
            </View>

            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Действия</Text>
              <TouchableOpacity style={styles.secondaryBtn} onPress={() => run('reminders')}>
                <Text style={styles.secondaryText}>📋 Показать список</Text>
              </TouchableOpacity>
              <View style={styles.row}>
                <TextInput
                  style={[styles.input, { flex: 1 }]}
                  value={cancelId}
                  onChangeText={setCancelId}
                  placeholder="ID напоминания"
                  placeholderTextColor="#555"
                />
                <TouchableOpacity
                  style={styles.dangerBtn}
                  onPress={() => cancelId && run(`remind_cancel ${cancelId}`)}
                >
                  <Text style={styles.dangerText}>🗑</Text>
                </TouchableOpacity>
              </View>
            </View>

            {loading && (
              <ActivityIndicator color="#FF8C42" style={{ marginVertical: 12 }} />
            )}

            {result && (
              <View style={styles.resultBox}>
                <Text style={styles.resultText}>{result}</Text>
              </View>
            )}
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: '#000000bb',
    justifyContent: 'flex-end',
  },
  card: {
    backgroundColor: '#12122a',
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    padding: 20,
    maxHeight: '85%',
    borderTopWidth: 1,
    borderTopColor: '#2a2a4a',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  title: { color: '#FF8C42', fontSize: 18, fontWeight: '700' },
  close: { color: '#8888aa', fontSize: 22 },
  section: {
    backgroundColor: '#0f0f2a',
    borderRadius: 14,
    padding: 14,
    marginBottom: 12,
    borderWidth: 1,
    borderColor: '#1a1a3e',
  },
  sectionTitle: { color: '#e0e0f0', fontWeight: '700', marginBottom: 10, fontSize: 14 },
  label: { color: '#8888aa', fontSize: 12, marginBottom: 4, marginTop: 8 },
  input: {
    backgroundColor: '#1a1a3e',
    borderRadius: 10,
    padding: 10,
    color: '#e0e0f0',
    borderWidth: 1,
    borderColor: '#2a2a4a',
  },
  primaryBtn: {
    backgroundColor: '#FF8C42',
    borderRadius: 10,
    padding: 12,
    alignItems: 'center',
    marginTop: 10,
  },
  primaryText: { color: '#0a0a1a', fontWeight: '700' },
  secondaryBtn: {
    backgroundColor: '#1a1a3e',
    borderRadius: 10,
    padding: 12,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#2a2a4a',
  },
  secondaryText: { color: '#e0e0f0' },
  row: { flexDirection: 'row', gap: 8, marginTop: 8 },
  dangerBtn: {
    backgroundColor: '#3a1010',
    borderRadius: 10,
    paddingHorizontal: 14,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: '#5a2020',
  },
  dangerText: { color: '#ff6666', fontSize: 16 },
  resultBox: {
    backgroundColor: '#0a0a1a',
    borderRadius: 10,
    padding: 12,
    borderWidth: 1,
    borderColor: '#2a2a4a',
    marginBottom: 20,
  },
  resultText: { color: '#e0e0f0', fontSize: 13 },
});
