/**
 * Frontend Vertical Configuration
 * Defines features, routes, and UI settings for each vertical/domain.
 */

export const VERTICAL_CONFIGS = {
  private_equity: {
    name: 'Private Equity',
    slug: 'private_equity',
    description: 'Investment analysis and deal flow platform',
    features: [
      'document_library',
      'free_form_chat',
      'workflows',
      'extraction',
      'comparison', // Future
    ],
    navigationItems: [
      { label: 'Library', path: '/pe/library', icon: 'book' },
      { label: 'Chat', path: '/pe/chat', icon: 'message-circle' },
      { label: 'Workflows', path: '/pe/workflows', icon: 'flow' },
      { label: 'Extraction', path: '/pe/extraction', icon: 'zap' },
      {
        label: 'Comparison',
        path: '/pe/comparison',
        icon: 'git-compare',
        comingSoon: true,
      },
    ],
    theme: {
      primary: '#1a365d',
      secondary: '#2d3748',
    },
  },
  real_estate: {
    name: 'Real Estate',
    slug: 'real_estate',
    description: 'Real estate analysis with Excel template filling',
    features: [
      'document_library',
      'free_form_chat',
      'excel_templates',
      'template_filling',
    ],
    navigationItems: [
      { label: 'Library', path: '/re/library', icon: 'book' },
      { label: 'Chat', path: '/re/chat', icon: 'message-circle' },
      { label: 'Templates', path: '/re/templates', icon: 'file-spreadsheet' },
      { label: 'Fills', path: '/re/fills', icon: 'table' },
    ],
    theme: {
      primary: '#2d5016',
      secondary: '#4a7c59',
    },
  },
};

/**
 * Get vertical configuration by slug
 */
export function getVerticalConfig(vertical) {
  return VERTICAL_CONFIGS[vertical];
}

/**
 * Check if a feature is enabled for a vertical
 */
export function isFeatureEnabled(vertical, feature) {
  const config = getVerticalConfig(vertical);
  return config ? config.features.includes(feature) : false;
}

/**
 * Get navigation items for a vertical
 */
export function getVerticalNavigation(vertical) {
  const config = getVerticalConfig(vertical);
  return config ? config.navigationItems : [];
}

/**
 * Get all vertical slugs
 */
export function getAllVerticals() {
  return Object.keys(VERTICAL_CONFIGS);
}

/**
 * Get theme for a vertical
 */
export function getVerticalTheme(vertical) {
  const config = getVerticalConfig(vertical);
  return config ? config.theme : {};
}
