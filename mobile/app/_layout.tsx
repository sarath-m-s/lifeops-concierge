import React from 'react';
import { Tabs } from 'expo-router';
import { View, Text, StyleSheet } from 'react-native';
import { PlanProvider } from '../state/PlanContext';
import { Icons } from '../constants/icons';
import { Colors, Radius, Spacing, Typography } from '../constants/theme';

export default function RootLayout() {
  return (
    <PlanProvider>
      <Tabs
        screenOptions={{
          headerStyle: { backgroundColor: Colors.surface },
          headerShadowVisible: false,
          headerTintColor: Colors.textPrimary,
          headerTitleStyle: Typography.heading,
          tabBarActiveTintColor: Colors.brand,
          tabBarInactiveTintColor: Colors.textMuted,
          tabBarStyle: {
            backgroundColor: Colors.surface,
            borderTopColor: Colors.border,
            height: 64,
            paddingBottom: 8,
            paddingTop: 6,
          },
          tabBarLabelStyle: Typography.overline,
        }}
      >
        <Tabs.Screen
          name="index"
          options={{
            title: 'Chat',
            headerTitle: 'LifeOps Concierge',
            headerRight: () => <PoweredBy />,
            tabBarIcon: ({ color }) => <Icons.chat size={21} color={color} strokeWidth={2} />,
          }}
        />
        <Tabs.Screen
          name="plan"
          options={{
            title: 'Plan',
            tabBarIcon: ({ color }) => <Icons.plan size={21} color={color} strokeWidth={2} />,
          }}
        />
        <Tabs.Screen
          name="settings"
          options={{
            title: 'Settings',
            tabBarIcon: ({ color }) => <Icons.settings size={21} color={color} strokeWidth={2} />,
          }}
        />
      </Tabs>
    </PlanProvider>
  );
}

function PoweredBy() {
  return (
    <View style={styles.badge}>
      <View style={styles.dot} />
      <Text style={styles.label}>Swiggy</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: Spacing.xs,
    marginRight: Spacing.lg,
    paddingHorizontal: Spacing.sm,
    paddingVertical: 3,
    borderRadius: Radius.full,
    backgroundColor: Colors.brandTint,
    borderWidth: 1,
    borderColor: Colors.brand + '33',
  },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: Colors.brand },
  label: { ...Typography.overline, color: Colors.brand, textTransform: 'uppercase' },
});
