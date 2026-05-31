import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { colors, fonts, spacing, radii } from '../theme';
import { Sentry } from '../sentry';

// Ловит ошибку рендера в дереве, чтобы краш не давал чёрный/белый экран.
// Показывает дружелюбный фолбэк с кнопкой «попробовать снова».

interface Props { children: React.ReactNode }
interface State { hasError: boolean }

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: unknown) {
    console.error('Mira UI error:', error);
    Sentry.captureException(error);
  }

  render() {
    if (this.state.hasError) {
      return (
        <View style={styles.container}>
          <Text style={styles.title}>Что-то сломалось</Text>
          <Text style={styles.text}>
            Мира столкнулась с ошибкой в интерфейсе. Твои данные целы — можно попробовать снова.
          </Text>
          <TouchableOpacity style={styles.btn} onPress={() => this.setState({ hasError: false })}>
            <Text style={styles.btnText}>Попробовать снова</Text>
          </TouchableOpacity>
        </View>
      );
    }
    return this.props.children;
  }
}

const styles = StyleSheet.create({
  container: {
    flex: 1, alignItems: 'center', justifyContent: 'center',
    backgroundColor: colors.bg.page, padding: spacing['3xl'],
  },
  title: {
    fontFamily: fonts.serif, fontSize: 24, color: colors.gold.DEFAULT, marginBottom: spacing.md,
  },
  text: {
    fontFamily: fonts.sans, fontSize: 14, color: colors.text.dim,
    textAlign: 'center', marginBottom: spacing['2xl'], lineHeight: 20,
  },
  btn: {
    backgroundColor: colors.gold.DEFAULT, paddingHorizontal: spacing['2xl'],
    paddingVertical: spacing.md, borderRadius: radii.button,
  },
  btnText: { fontFamily: fonts.sans, fontSize: 14, fontWeight: '600', color: colors.bg.page },
});
