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
      { label: 'Dashboard', path: '/pe', icon: 'dashboard' },
      { label: 'Library', path: '/library', icon: 'book' },
      { label: 'Chat', path: '/chat', icon: 'message-circle' },
      { label: 'Workflows', path: '/workflows', icon: 'flow' },
      { label: 'Extract', path: '/extract', icon: 'zap' },
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
      { label: 'Dashboard', path: '/re', icon: 'dashboard' },
      { label: 'Templates', path: '/re/templates', icon: 'file-spreadsheet' },
      { label: 'Library', path: '/library', icon: 'book' },
      { label: 'Chat', path: '/chat', icon: 'message-circle' },
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
