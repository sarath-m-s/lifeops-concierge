import React, { useEffect, useRef } from 'react';
import { TouchableOpacity, View, Text, StyleSheet, Animated } from 'react-native';
import { Colors, BorderRadius } from '../constants/theme';

type VoiceState = 'idle' | 'listening' | 'processing';

interface Props {
  state: VoiceState;
  onPress: () => void;
}

export function VoiceButton({ state, onPress }: Props) {
  const pulse = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    if (state === 'listening') {
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulse, { toValue: 1.3, duration: 600, useNativeDriver: true }),
          Animated.timing(pulse, { toValue: 1, duration: 600, useNativeDriver: true }),
        ])
      ).start();
    } else {
      pulse.stopAnimation();
      pulse.setValue(1);
    }
  }, [state, pulse]);

  const bgColor =
    state === 'listening' ? '#FF3B30' :
    state === 'processing' ? Colors.swiggyOrange :
    Colors.swiggyOrange;

  const icon =
    state === 'idle' ? '🎙️' :
    state === 'listening' ? '⏹' :
    '⏳';

  return (
    <TouchableOpacity onPress={onPress} disabled={state === 'processing'} activeOpacity={0.8}>
      <Animated.View style={[styles.outer, state === 'listening' && { transform: [{ scale: pulse }] }]}>
        <View style={[styles.button, { backgroundColor: bgColor }]}>
          <Text style={styles.icon}>{icon}</Text>
        </View>
      </Animated.View>
      {state === 'processing' && <Text style={styles.label}>Transcribing...</Text>}
      {state === 'listening' && <Text style={styles.label}>Listening...</Text>}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  outer: {
    alignItems: 'center',
  },
  button: {
    width: 44,
    height: 44,
    borderRadius: BorderRadius.full,
    alignItems: 'center',
    justifyContent: 'center',
  },
  icon: {
    fontSize: 20,
  },
  label: {
    fontSize: 10,
    color: Colors.textMuted,
    marginTop: 2,
    textAlign: 'center',
  },
});
