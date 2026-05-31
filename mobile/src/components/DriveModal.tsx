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
  Linking,
} from 'react-native';
import type { MiraClient } from '../api/mira-client';

interface Props {
  visible: boolean;
  onClose: () => void;
  client: MiraClient | null;
}

export function DriveModal({ visible, onClose, client }: Props) {
  const [folder, setFolder] = useState('');
  const [fileId, setFileId] = useState('');
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [authUrl, setAuthUrl] = useState<string | null>(null);

  useEffect(() => {
    if (visible) {
      setFolder('');
      setFileId('');
      setResult(null);
      setAuthUrl(null);
      setLoading(false);
    }
  }, [visible]);

  const run = useCallback(async (cmd: string, expectedTypes?: string[]) => {
    if (!client) return;
    setLoading(true);
    setResult(null);
    setAuthUrl(null);
    try {
      const types = (expectedTypes || ['system', 'gdrive_auth_url']) as any;
      const msg = await client.sendCommandAwait(cmd, types, 15000);
      if (msg.type === 'gdrive_auth_url') {
        setAuthUrl(msg.url);
      } else if ('content' in msg) {
        setResult(msg.content);
      }
    } catch {
      setResult('Ошибка: нет ответа от сервера');
    } finally {
      setLoading(false);
    }
  }, [client]);

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.overlay}>
        <View style={styles.card}>
          <View style={styles.header}>
            <Text style={styles.title}>☁️ Google Drive</Text>
            <TouchableOpacity onPress={onClose}>
              <Text style={styles.close}>✕</Text>
            </TouchableOpacity>
          </View>

          <ScrollView showsVerticalScrollIndicator={false}>
            <TouchableOpacity style={styles.actionBtn} onPress={() => run('gdrive_login')}>
              <Text style={styles.actionText}>🔗 Привязать Google Drive</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.actionBtn} onPress={() => run('gdrive_status')}>
              <Text style={styles.actionText}>📊 Статус привязки</Text>
            </TouchableOpacity>

            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Список файлов</Text>
              <View style={styles.row}>
                <TextInput
                  style={[styles.input, { flex: 1 }]}
                  value={folder}
                  onChangeText={setFolder}
                  placeholder="Папка (опционально)"
                  placeholderTextColor="#555"
                />
                <TouchableOpacity
                  style={styles.primaryBtn}
                  onPress={() => run(folder ? `gdrive_list ${folder}` : 'gdrive_list')}
                >
                  <Text style={styles.primaryText}>📂</Text>
                </TouchableOpacity>
              </View>
            </View>

            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Скачать файл</Text>
              <View style={styles.row}>
                <TextInput
                  style={[styles.input, { flex: 1 }]}
                  value={fileId}
                  onChangeText={setFileId}
                  placeholder="ID файла"
                  placeholderTextColor="#555"
                />
                <TouchableOpacity
                  style={styles.primaryBtn}
                  onPress={() => fileId && run(`gdrive_get ${fileId}`)}
                >
                  <Text style={styles.primaryText}>⬇</Text>
                </TouchableOpacity>
              </View>
            </View>

            {loading && (
              <ActivityIndicator color="#FF8C42" style={{ marginVertical: 12 }} />
            )}

            {authUrl && (
              <View style={styles.resultBox}>
                <Text style={styles.resultLabel}>Открой ссылку для авторизации:</Text>
                <Text style={styles.link} onPress={() => Linking.openURL(authUrl)}>
                  {authUrl}
                </Text>
              </View>
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
  actionBtn: {
    backgroundColor: '#0f0f2a',
    borderRadius: 12,
    padding: 12,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#1a1a3e',
    alignItems: 'center',
  },
  actionText: { color: '#e0e0f0', fontSize: 14 },
  section: {
    backgroundColor: '#0f0f2a',
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: '#1a1a3e',
  },
  sectionTitle: { color: '#e0e0f0', fontWeight: '700', marginBottom: 8, fontSize: 14 },
  row: { flexDirection: 'row', gap: 8 },
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
    paddingHorizontal: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryText: { color: '#0a0a1a', fontWeight: '700', fontSize: 16 },
  resultBox: {
    backgroundColor: '#0a0a1a',
    borderRadius: 10,
    padding: 12,
    borderWidth: 1,
    borderColor: '#2a2a4a',
    marginBottom: 20,
  },
  resultLabel: { color: '#8888aa', fontSize: 12, marginBottom: 6 },
  resultText: { color: '#e0e0f0', fontSize: 13 },
  link: {
    color: '#FF8C42',
    fontSize: 12,
    textDecorationLine: 'underline',
  },
});
