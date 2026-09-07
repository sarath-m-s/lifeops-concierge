/**
 * Design tokens. Values here are the only source of colour, spacing, and type
 * size in the app — components never hardcode a hex or a pixel value.
 */

const swiggy = '#FC8019';

export const Colors = {
  brand: swiggy,
  brandDark: '#E06A0B',
  brandTint: '#FFF3E8',

  // Per-service accents. Each service owns a colour so a glance at a card tells
  // you which Swiggy surface it came from without reading the label.
  dineout: '#7C4DFF',
  food: swiggy,
  instamart: '#0F9D58',

  background: '#FAFAF8',
  surface: '#FFFFFF',
  surfaceSunken: '#F2F1EE',

  textPrimary: '#16181D',
  textSecondary: '#5B6070',
  textMuted: '#8B909E',
  textInverse: '#FFFFFF',

  border: '#E6E5E1',
  borderStrong: '#D2D1CC',

  success: '#0F9D58',
  successTint: '#E8F6EF',
  error: '#D93025',
  errorTint: '#FDECEA',
  warning: '#F29900',
  warningTint: '#FEF5E6',
} as const;

export const ServiceColor: Record<string, string> = {
  dineout: Colors.dineout,
  food: Colors.food,
  instamart: Colors.instamart,
};

export const ServiceLabel: Record<string, string> = {
  dineout: 'Swiggy Dineout',
  food: 'Swiggy Food',
  instamart: 'Swiggy Instamart',
};

/** 4pt base scale. */
export const Spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
  xxxl: 48,
} as const;

export const Typography = {
  display: { fontSize: 28, lineHeight: 34, fontWeight: '700' as const, letterSpacing: -0.5 },
  title: { fontSize: 20, lineHeight: 26, fontWeight: '700' as const, letterSpacing: -0.3 },
  heading: { fontSize: 17, lineHeight: 23, fontWeight: '600' as const, letterSpacing: -0.2 },
  body: { fontSize: 15, lineHeight: 22, fontWeight: '400' as const },
  bodyStrong: { fontSize: 15, lineHeight: 22, fontWeight: '600' as const },
  caption: { fontSize: 13, lineHeight: 18, fontWeight: '400' as const },
  captionStrong: { fontSize: 13, lineHeight: 18, fontWeight: '600' as const },
  overline: { fontSize: 11, lineHeight: 14, fontWeight: '700' as const, letterSpacing: 0.6 },
} as const;

export const Radius = {
  sm: 8,
  md: 12,
  lg: 16,
  xl: 20,
  full: 999,
} as const;

/** Cross-platform elevation — iOS shadow plus the Android elevation equivalent. */
export const Elevation = {
  none: {},
  card: {
    shadowColor: '#16181D',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.06,
    shadowRadius: 3,
    elevation: 2,
  },
  raised: {
    shadowColor: '#16181D',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.1,
    shadowRadius: 12,
    elevation: 6,
  },
  sheet: {
    shadowColor: '#16181D',
    shadowOffset: { width: 0, height: -4 },
    shadowOpacity: 0.12,
    shadowRadius: 20,
    elevation: 16,
  },
} as const;
