import { Tabs } from 'expo-router';
import { Colors } from '../constants/theme';

export default function RootLayout() {
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: Colors.surface },
        headerTintColor: Colors.textPrimary,
        headerTitleStyle: { fontWeight: '700' },
        tabBarActiveTintColor: Colors.swiggyOrange,
        tabBarInactiveTintColor: Colors.tabBarInactive,
        tabBarStyle: {
          backgroundColor: Colors.tabBar,
          borderTopColor: Colors.border,
          paddingBottom: 4,
          height: 60,
        },
        tabBarLabelStyle: { fontSize: 11, fontWeight: '600' },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Chat',
          tabBarLabel: 'Chat',
          tabBarIcon: ({ color }) => <TabIcon label="💬" color={color} />,
          headerTitle: 'LifeOps Concierge',
          headerRight: () => <SwiggyHeaderBadge />,
        }}
      />
      <Tabs.Screen
        name="plan"
        options={{
          title: 'My Plan',
          tabBarLabel: 'Plan',
          tabBarIcon: ({ color }) => <TabIcon label="📋" color={color} />,
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: 'Settings',
          tabBarLabel: 'Settings',
          tabBarIcon: ({ color }) => <TabIcon label="⚙️" color={color} />,
        }}
      />
    </Tabs>
  );
}

// Inline tiny components — avoids extra files for layout-only UI
import { Text, View, StyleSheet } from 'react-native';

function TabIcon({ label, color }: { label: string; color: string }) {
  return <Text style={{ fontSize: 20 }}>{label}</Text>;
}

function SwiggyHeaderBadge() {
  return (
    <View style={hdrStyles.badge}>
      <View style={hdrStyles.dot} />
      <Text style={hdrStyles.text}>Powered by Swiggy</Text>
    </View>
  );
}

const hdrStyles = StyleSheet.create({
  badge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFF4EC',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 999,
    marginRight: 12,
    borderWidth: 1,
    borderColor: '#FFD4B0',
  },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: Colors.swiggyOrange, marginRight: 4 },
  text: { fontSize: 11, color: Colors.swiggyOrange, fontWeight: '600' },
});
