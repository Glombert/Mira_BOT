import React, { useState, useEffect, useCallback } from 'react';
import {
  Modal,
  View,
  Text,
  TouchableOpacity,
  ScrollView,
  ActivityIndicator,
  TextInput,
  Alert,
  StyleSheet,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { colors, spacing, radii, typography, fonts } from '../theme';
import { MiraIcon } from './ui/MiraIcon';
import { APP_VERSION } from '../config';
import { TIMEZONES, tzLabel } from './data/timezones';
import type { MiraClient } from '../api/mira-client';
import type { ProfileData } from '../types';

interface Props {
  visible: boolean;
  onClose: () => void;
  client: MiraClient | null;
  /** Режим первичной анкеты после одобрения (показываем «Пропустить»). */
  onboarding?: boolean;
}

const ROLE_LABEL: Record<string, string> = {
  owner: 'Владелец', regular: 'Одобрен', guest: 'Гость',
  rejected: 'Отклонён', blacklisted: 'Чёрный список', blocked: 'Заблокирован', kid: 'Детский режим',
};

const MANNER_FALLBACK = ['тёплая', 'вдумчивая', 'немногословная', 'игривая', 'формальная', 'дерзкая', 'заботливая', 'прямая'];

export function ProfileModal({ visible, onClose, client, onboarding = false }: Props) {
  const insets = useSafeAreaInsets();
  const [profile, setProfile] = useState<ProfileData | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [tzPickerOpen, setTzPickerOpen] = useState(false);

  // поля анкеты
  const [addressing, setAddressing] = useState('');
  const [addressForm, setAddressForm] = useState('');
  const [manner, setManner] = useState<string[]>([]);
  const [origin, setOrigin] = useState('');
  const [occupation, setOccupation] = useState('');
  const [notes, setNotes] = useState('');
  const [timezone, setTimezone] = useState('');
  const [filledByMira, setFilledByMira] = useState<string[]>([]);

  const load = useCallback(async () => {
    if (!client) return;
    setLoading(true);
    try {
      const msg = await client.sendCommandAwait('profile_data', ['profile_data'], 12000);
      if ('profile' in msg) {
        const p = msg.profile;
        setProfile(p);
        setAddressing(p.addressing || p.name || '');
        setAddressForm(p.address_form || '');
        setManner(p.manner || []);
        setOrigin(p.origin || '');
        setOccupation(p.occupation || '');
        setNotes(p.notes || '');
        setTimezone(p.timezone || '');
        setFilledByMira(p.filled_by_mira || []);
      }
    } catch {
      /* no-op */
    } finally {
      setLoading(false);
    }
  }, [client]);

  useEffect(() => {
    if (visible) { setTzPickerOpen(false); load(); }
  }, [visible, load]);

  const toggleManner = useCallback((m: string) => {
    setManner((prev) => (prev.includes(m) ? prev.filter((x) => x !== m) : [...prev, m]));
  }, []);

  const save = useCallback((skip = false) => {
    if (!client) return;
    setSaving(true);
    client.saveProfile(skip ? {} : {
      addressing: addressing.trim(),
      address_form: addressForm,
      manner,
      origin: origin.trim(),
      occupation: occupation.trim(),
      notes: notes.trim(),
      timezone: timezone.trim(),
    });
    // optimistic — закрываем сразу (ack приходит отдельным типом, не в чат)
    setTimeout(() => { setSaving(false); onClose(); }, 250);
  }, [client, addressing, addressForm, manner, origin, occupation, notes, timezone, onClose]);

  const confirmForget = useCallback(() => {
    Alert.alert('Забыть меня?',
      'Мира удалит профиль, историю беседы и всё, что запомнила о тебе. Это необратимо.',
      [
        { text: 'Отмена', style: 'cancel' },
        { text: 'Продолжить', style: 'destructive', onPress: () => {
          Alert.alert('Точно удалить всё?', 'Последнее подтверждение. Восстановить будет нельзя.',
            [
              { text: 'Отмена', style: 'cancel' },
              { text: 'Забудь меня', style: 'destructive', onPress: () => { client?.sendCommand('forget'); onClose(); } },
            ]);
        } },
      ]);
  }, [client, onClose]);

  const initial = (addressing || profile?.name || '?').trim().charAt(0).toUpperCase() || '?';
  const roleLabel = profile ? ROLE_LABEL[profile.role] || profile.role : '';
  const mannerOptions = profile?.manner_options?.length ? profile.manner_options : MANNER_FALLBACK;

  return (
    <Modal visible={visible} animationType="slide" transparent onRequestClose={onClose}>
      <View style={styles.overlay}>
        <TouchableOpacity style={StyleSheet.absoluteFill} activeOpacity={1} onPress={onClose} />
        <View style={[styles.card, { paddingBottom: insets.bottom + spacing.lg }]}>
          <View style={styles.header}>
            <Text style={styles.title}>{onboarding ? 'Расскажи о себе' : 'Профиль'}</Text>
            <TouchableOpacity onPress={onClose} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
              <Text style={styles.close}>✕</Text>
            </TouchableOpacity>
          </View>

          {loading && !profile ? (
            <ActivityIndicator color={colors.gold.DEFAULT} style={{ marginVertical: spacing['3xl'] }} />
          ) : (
            <ScrollView showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">
              {onboarding && (
                <Text style={styles.onbHint}>
                  Заполни, если хочешь — так Мира станет ближе именно тебе. Всё необязательно.
                </Text>
              )}

              {/* Hero */}
              {!onboarding && profile && (
                <>
                  <View style={styles.hero}>
                    <View style={styles.avatar}><Text style={styles.avatarText}>{initial}</Text></View>
                    <Text style={styles.name} numberOfLines={1}>{addressing || profile.name || 'Без имени'}</Text>
                    <View style={styles.roleChip}><Text style={styles.roleChipText}>{roleLabel}</Text></View>
                  </View>
                  <Text style={styles.bandLabel}>наша связь</Text>
                  <View style={styles.statsGrid}>
                    <Stat value={String(profile.days_together)} label="дней" mono />
                    <Stat value={String(profile.conversations)} label="бесед" mono />
                    <Stat value={String(profile.memory_facts)} label="фактов" mono />
                    <Stat value={APP_VERSION} label="версия" mono />
                  </View>
                  {profile.summary ? (
                    <View style={styles.observation}>
                      <Text style={styles.observationLabel}>✦ что Мира знает о тебе</Text>
                      <Text style={styles.observationText}>{profile.summary}</Text>
                    </View>
                  ) : null}
                </>
              )}

              {/* Анкета */}
              <Text style={styles.sectionLabel}>✦ КАК ОБРАЩАТЬСЯ</Text>
              <View style={styles.section}>
                <TextInput style={styles.input} value={addressing} onChangeText={setAddressing}
                  placeholder="Имя или как тебя называть" placeholderTextColor={colors.text.faint} />
                <View style={styles.segment}>
                  {['ты', 'вы'].map((f) => (
                    <TouchableOpacity key={f} style={[styles.segBtn, addressForm === f && styles.segBtnActive]}
                      onPress={() => setAddressForm(addressForm === f ? '' : f)} activeOpacity={0.7}>
                      <Text style={[styles.segText, addressForm === f && styles.segTextActive]}>на «{f}»</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>

              <Text style={styles.sectionLabel}>✦ МАНЕРА МИРЫ</Text>
              <Text style={styles.fieldHint}>Мира останется собой — это лишь тон под тебя</Text>
              <View style={styles.chips}>
                {mannerOptions.map((m) => {
                  const on = manner.includes(m);
                  return (
                    <TouchableOpacity key={m} style={[styles.chip, on && styles.chipOn]} onPress={() => toggleManner(m)} activeOpacity={0.7}>
                      <Text style={[styles.chipText, on && styles.chipTextOn]}>{m}</Text>
                    </TouchableOpacity>
                  );
                })}
              </View>

              <Text style={styles.sectionLabel}>✦ О ТЕБЕ</Text>
              {filledByMira.length > 0 && (
                <Text style={styles.fieldHint}>✦ часть полей Мира заполнила сама — поправь, если не так</Text>
              )}
              <View style={styles.section}>
                <Text style={styles.label}>Откуда{filledByMira.includes('origin') ? '  ✦ от Миры' : ''}</Text>
                <TextInput style={styles.input} value={origin} onChangeText={setOrigin}
                  placeholder="Город / страна" placeholderTextColor={colors.text.faint} />
                <Text style={styles.label}>Чем занимаешься{filledByMira.includes('occupation') ? '  ✦ от Миры' : ''}</Text>
                <TextInput style={styles.input} value={occupation} onChangeText={setOccupation}
                  placeholder="Кем работаешь / чем живёшь" placeholderTextColor={colors.text.faint} />
                <Text style={styles.label}>Часовой пояс</Text>
                <TouchableOpacity style={styles.pickerBtn} onPress={() => setTzPickerOpen(true)} activeOpacity={0.7}>
                  <Text style={[styles.pickerText, !timezone && { color: colors.text.faint }]} numberOfLines={1}>
                    {timezone ? tzLabel(timezone) : 'выбрать из списка'}
                  </Text>
                  <Text style={styles.pencil}>▾</Text>
                </TouchableOpacity>
                <Text style={styles.label}>Что ещё рассказать (по желанию)</Text>
                <TextInput style={[styles.input, styles.textarea]} value={notes} onChangeText={setNotes}
                  placeholder="Интересы, привычки, что важно знать…" placeholderTextColor={colors.text.faint}
                  multiline />
              </View>

              {/* Save */}
              <TouchableOpacity style={styles.saveBtn} onPress={() => save(false)} disabled={saving} activeOpacity={0.8}>
                {saving ? <ActivityIndicator color={colors.bg.page} /> : <Text style={styles.saveText}>Сохранить</Text>}
              </TouchableOpacity>
              {onboarding && (
                <TouchableOpacity style={styles.skipBtn} onPress={() => save(true)} activeOpacity={0.7}>
                  <Text style={styles.skipText}>Пропустить</Text>
                </TouchableOpacity>
              )}

              {/* Интеграции + Опасная зона — только в обычном режиме */}
              {!onboarding && profile && (
                <>
                  <Text style={styles.sectionLabel}>✦ ИНТЕГРАЦИИ</Text>
                  <View style={styles.section}>
                    <View style={styles.driveRow}>
                      <MiraIcon name="cloud" color={colors.text.dim} size={16} />
                      <Text style={[styles.rowLabel, { marginLeft: spacing.sm }]}>Google Drive</Text>
                      <View style={styles.driveStatus}>
                        {profile.gdrive_linked && <View style={styles.dot} />}
                        <Text style={[styles.rowValue, profile.gdrive_linked && { color: colors.sage }]} numberOfLines={1}>
                          {profile.gdrive_linked ? (profile.gdrive_email || 'подключено') : 'не подключено'}
                        </Text>
                      </View>
                    </View>
                  </View>

                  <Text style={[styles.sectionLabel, { color: colors.rose }]}>⚠ ОПАСНАЯ ЗОНА</Text>
                  <TouchableOpacity style={styles.dangerBtn} activeOpacity={0.7} onPress={confirmForget}>
                    <Text style={styles.dangerText}>Забыть меня</Text>
                  </TouchableOpacity>
                </>
              )}
            </ScrollView>
          )}
        </View>
      </View>

      {/* TZ picker */}
      <Modal visible={tzPickerOpen} animationType="fade" transparent onRequestClose={() => setTzPickerOpen(false)}>
        <View style={styles.overlay}>
          <TouchableOpacity style={StyleSheet.absoluteFill} activeOpacity={1} onPress={() => setTzPickerOpen(false)} />
          <View style={[styles.card, { maxHeight: '70%', paddingBottom: insets.bottom + spacing.lg }]}>
            <View style={styles.header}>
              <Text style={styles.title}>Часовой пояс</Text>
              <TouchableOpacity onPress={() => setTzPickerOpen(false)} hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}>
                <Text style={styles.close}>✕</Text>
              </TouchableOpacity>
            </View>
            <ScrollView showsVerticalScrollIndicator={false}>
              {TIMEZONES.map((t) => (
                <TouchableOpacity key={t.value} style={[styles.tzRow, timezone === t.value && styles.tzRowOn]}
                  onPress={() => { setTimezone(t.value); setTzPickerOpen(false); }} activeOpacity={0.7}>
                  <Text style={[styles.tzRowText, timezone === t.value && { color: colors.gold.DEFAULT }]}>{t.label}</Text>
                  {timezone === t.value && <Text style={styles.tzCheck}>✓</Text>}
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>
        </View>
      </Modal>
    </Modal>
  );
}

function Stat({ value, label, mono }: { value: string; label: string; mono?: boolean }) {
  return (
    <View style={styles.stat}>
      <Text style={[styles.statValue, mono && { fontFamily: fonts.mono }]} numberOfLines={1}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: '#000000bb', justifyContent: 'flex-end' },
  card: {
    backgroundColor: colors.bg.surface,
    borderTopLeftRadius: 24, borderTopRightRadius: 24,
    paddingHorizontal: spacing.lg, paddingTop: spacing.lg,
    maxHeight: '92%', borderTopWidth: 1, borderTopColor: colors.border.subtle,
  },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: spacing.md },
  title: { ...typography.topbarName, color: colors.gold.DEFAULT, fontStyle: 'italic' },
  close: { color: colors.text.muted, fontSize: 20, paddingHorizontal: 4 },
  onbHint: { ...typography.body, color: colors.text.dim, marginBottom: spacing.md },

  hero: { alignItems: 'center', marginBottom: spacing.lg },
  avatar: {
    width: 72, height: 72, borderRadius: 36, backgroundColor: colors.gold.dim,
    borderWidth: 1, borderColor: colors.border.strong, alignItems: 'center', justifyContent: 'center', marginBottom: spacing.sm,
  },
  avatarText: { fontFamily: fonts.serif, fontSize: 32, color: colors.gold.DEFAULT },
  name: { ...typography.welcomeGreeting, fontSize: 26, lineHeight: 30, color: colors.text.primary },
  roleChip: { marginTop: spacing.xs, paddingHorizontal: spacing.md, paddingVertical: 3, borderRadius: radii.pill, backgroundColor: colors.gold.dim, borderWidth: 1, borderColor: colors.border.strong },
  roleChipText: { ...typography.status, color: colors.gold.DEFAULT },

  bandLabel: { ...typography.welcomePrompt, color: colors.text.dim, marginBottom: spacing.sm },
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginBottom: spacing.lg },
  stat: { flexBasis: '47%', flexGrow: 1, backgroundColor: colors.bg.page, borderRadius: radii.card, borderWidth: 1, borderColor: colors.border.subtle, paddingVertical: spacing.md, alignItems: 'center' },
  statValue: { fontFamily: fonts.mono, fontSize: 18, color: colors.gold.DEFAULT },
  statLabel: { ...typography.monoHint, color: colors.text.muted, marginTop: 2, letterSpacing: 0.6 },

  observation: { backgroundColor: colors.mystic.soft, borderRadius: radii.card, borderWidth: 1, borderColor: 'rgba(185, 163, 255, 0.24)', padding: spacing.md, marginBottom: spacing.lg },
  observationLabel: { ...typography.status, color: colors.mystic.DEFAULT, marginBottom: 6 },
  observationText: { ...typography.memoryFact, color: colors.text.primary },

  sectionLabel: { ...typography.sectionLabel, color: colors.text.muted, marginBottom: spacing.sm, marginLeft: 2 },
  fieldHint: { ...typography.monoHint, color: colors.text.muted, marginBottom: spacing.sm, marginLeft: 2 },
  section: { backgroundColor: colors.bg.page, borderRadius: radii.card, borderWidth: 1, borderColor: colors.border.subtle, padding: spacing.md, marginBottom: spacing.lg },
  label: { ...typography.monoHint, color: colors.text.muted, marginBottom: 4, marginTop: spacing.sm, letterSpacing: 0.6 },
  input: {
    backgroundColor: colors.bg.surface, borderRadius: radii.button, borderWidth: 1, borderColor: colors.border.subtle,
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm, color: colors.text.primary, fontFamily: fonts.sans,
  },
  textarea: { minHeight: 64, textAlignVertical: 'top' },

  segment: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm },
  segBtn: { flex: 1, paddingVertical: spacing.sm, borderRadius: radii.button, borderWidth: 1, borderColor: colors.border.subtle, alignItems: 'center' },
  segBtnActive: { backgroundColor: colors.gold.dim, borderColor: colors.border.strong },
  segText: { ...typography.body, color: colors.text.dim },
  segTextActive: { color: colors.gold.DEFAULT, fontWeight: '600' },

  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginBottom: spacing.lg },
  chip: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radii.pill, borderWidth: 1, borderColor: colors.border.subtle, backgroundColor: colors.bg.page },
  chipOn: { backgroundColor: 'rgba(185, 163, 255, 0.16)', borderColor: 'rgba(185, 163, 255, 0.5)' },
  chipText: { ...typography.body, color: colors.text.dim },
  chipTextOn: { color: colors.mystic.DEFAULT, fontWeight: '600' },

  pickerBtn: { flexDirection: 'row', alignItems: 'center', backgroundColor: colors.bg.surface, borderRadius: radii.button, borderWidth: 1, borderColor: colors.border.subtle, paddingHorizontal: spacing.md, paddingVertical: spacing.md },
  pickerText: { ...typography.body, color: colors.text.primary, flex: 1 },
  pencil: { color: colors.gold.DEFAULT, fontSize: 14, marginLeft: spacing.sm },

  saveBtn: { backgroundColor: colors.gold.DEFAULT, borderRadius: radii.button, paddingVertical: spacing.md, alignItems: 'center', marginBottom: spacing.sm },
  saveText: { color: colors.bg.page, fontFamily: fonts.sans, fontWeight: '700', fontSize: 15 },
  skipBtn: { paddingVertical: spacing.sm, alignItems: 'center', marginBottom: spacing.lg },
  skipText: { color: colors.text.dim, fontFamily: fonts.sans },

  driveRow: { flexDirection: 'row', alignItems: 'center' },
  rowLabel: { ...typography.body, color: colors.text.dim },
  rowValue: { ...typography.body, color: colors.text.primary },
  driveStatus: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 6 },
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: colors.sage },

  dangerBtn: { borderRadius: radii.button, borderWidth: 1, borderColor: 'rgba(232, 138, 138, 0.4)', backgroundColor: 'rgba(232, 138, 138, 0.08)', paddingVertical: spacing.md, alignItems: 'center', marginBottom: spacing.sm },
  dangerText: { color: colors.rose, fontFamily: fonts.sans, fontWeight: '600' },

  tzRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: spacing.md, paddingHorizontal: spacing.sm, borderBottomWidth: 1, borderBottomColor: colors.border.divider },
  tzRowOn: { backgroundColor: colors.gold.dim, borderRadius: radii.sidebarItem },
  tzRowText: { ...typography.body, color: colors.text.primary, flex: 1 },
  tzCheck: { color: colors.gold.DEFAULT, fontSize: 16 },
});
