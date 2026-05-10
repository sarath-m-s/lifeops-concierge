import React, { useState } from 'react';
import { View, Text, StyleSheet, TouchableOpacity } from 'react-native';
import { TimelineView } from '../components/TimelineView';
import { UIPayload } from '../types/agent';
import { Colors, Spacing, Typography } from '../constants/theme';

// Demo payload — used until a real backend response populates the plan
const DEMO_PAYLOAD: UIPayload = {
  type: 'timeline',
  title: 'Friday Evening Plan',
  items: [
    {
      step: 1,
      icon: '🍽️',
      category: 'dinner',
      title: 'Dinner at Toscano',
      subtitle: 'Indiranagar · ₹1,200 for two · 4.3★',
      time: '20:00',
      details: {
        restaurant: 'Toscano',
        address: '100 Feet Road, Indiranagar, Bengaluru - 560038',
        party_size: '2 people',
        time_slot: '8:00 PM Friday',
        offer: '20% off on drinks',
        amenities: 'Valet parking, Live music on weekends',
      },
      status: 'ready',
      source: 'dineout',
      powered_by: 'Swiggy Dineout',
      action: {
        action_type: 'book_table',
        params: {
          restaurant_id: 'din_toscano_indnr_001',
          slot_id: 'slot_din_toscano_indnr_001_2000_demo',
          party_size: 2,
        },
        display_summary: 'Book table for 2 at Toscano, 8:00 PM Friday',
      },
    },
    {
      step: 2,
      icon: '🍰',
      category: 'dessert',
      title: 'Dessert from Theobroma',
      subtitle: 'Delivery ~10:30 PM · 35 min',
      details: {
        restaurant: 'Theobroma',
        items: 'Chocolate Truffle Cake (₹450), Red Velvet Pastry (₹180)',
        delivery_time: '35 minutes',
        offer: 'Buy 2 get 1 free on pastries after 9 PM',
      },
      status: 'ready',
      source: 'food',
      powered_by: 'Swiggy Food',
      action: {
        action_type: 'place_food_order',
        params: {
          restaurant_id: 'food_theobroma_indnr_001',
          items: [{ item_id: 'itm_theo_choc_001', quantity: 1 }],
          cart_id: 'cart_food_mock_001',
          address_id: 'addr_mock_001',
        },
        display_summary: 'Order Chocolate Truffle Cake from Theobroma — ₹450',
      },
    },
    {
      step: 3,
      icon: '🛒',
      category: 'grocery',
      title: 'Morning Restock',
      subtitle: 'Coffee + Breakfast · 4 items · Delivery tomorrow 6–9 AM',
      details: {
        items: 'Sleepy Owl Cold Brew ₹299, Cothas Filter Coffee ₹185, Amul Milk ₹68, Britannia Bread ₹45',
        total: '₹597',
        delivery_slot: 'Tomorrow 6–9 AM',
      },
      status: 'ready',
      source: 'instamart',
      powered_by: 'Swiggy Instamart',
      action: {
        action_type: 'checkout_instamart',
        params: {
          cart_id: 'cart_instamart_mock_001',
          items: [
            { product_id: 'prd_sleepyowl_cold_001', quantity: 1 },
            { product_id: 'prd_cothas_filter_002', quantity: 1 },
            { product_id: 'prd_amul_milk_001', quantity: 1 },
            { product_id: 'prd_britannia_bread_002', quantity: 1 },
          ],
          address_id: 'addr_mock_001',
        },
        display_summary: 'Checkout 4 grocery items — ₹597',
      },
    },
  ],
};

// Plan is stored in module-level state so it persists between tab switches
// In Phase 3 this will be in a proper context/store
let _currentPayload: UIPayload = DEMO_PAYLOAD;

export function setPlanPayload(payload: UIPayload) {
  _currentPayload = payload;
}

export default function PlanScreen() {
  const [payload, setPayload] = useState<UIPayload>(_currentPayload);

  const resetDemo = () => {
    const reset: UIPayload = {
      ...DEMO_PAYLOAD,
      items: DEMO_PAYLOAD.items.map((i) => ({ ...i, status: 'ready' })),
    };
    _currentPayload = reset;
    setPayload(reset);
  };

  return (
    <View style={styles.container}>
      <TimelineView key={JSON.stringify(payload)} payload={payload} />
      <TouchableOpacity style={styles.resetBtn} onPress={resetDemo} activeOpacity={0.7}>
        <Text style={styles.resetText}>↺ Reset demo</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: Colors.background },
  resetBtn: {
    position: 'absolute',
    bottom: 24,
    right: 16,
    backgroundColor: Colors.surface,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: Colors.border,
    paddingHorizontal: Spacing.md,
    paddingVertical: Spacing.xs,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.08,
    shadowRadius: 4,
    elevation: 3,
  },
  resetText: {
    fontSize: Typography.fontSizeSm,
    color: Colors.textSecondary,
    fontWeight: '500',
  },
});
