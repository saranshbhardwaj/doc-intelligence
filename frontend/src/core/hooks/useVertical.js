/**
 * Custom hook for accessing vertical/domain information
 * Gets the current user's vertical from context or URL
 */
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  getVerticalConfig,
  isFeatureEnabled,
  getVerticalNavigation,
  getVerticalTheme,
  getAllVerticals,
} from '../../config/verticals.js';

/**
 * Extract vertical from URL path
 * /pe/* -> private_equity
 * /re/* -> real_estate
 */
function extractVerticalFromPath(pathname) {
  const match = pathname.match(/^\/(pe|re)\//);
  if (match === 'pe') return 'private_equity';
  if (match === 're') return 'real_estate';
  return null;
}

/**
 * Map vertical slug to URL prefix
 * private_equity -> /pe
 * real_estate -> /re
 */
function getVerticalPath(vertical) {
  const map = {
    private_equity: 'pe',
    real_estate: 're',
  };
  return `/${map[vertical] || 'pe'}`;
}

export function useVertical() {
  const navigate = useNavigate();
  const [vertical, setVertical] = useState(() => {
    // Try to get from localStorage (user's selected vertical)
    const saved = localStorage.getItem('userVertical');
    if (saved && getAllVerticals().includes(saved)) {
      return saved;
    }
    // Default to private_equity
    return 'private_equity';
  });

  // Get vertical from URL if available
  useEffect(() => {
    const pathname = window.location.pathname;
    const pathVertical = extractVerticalFromPath(pathname);
    if (pathVertical && pathVertical !== vertical) {
      setVertical(pathVertical);
      localStorage.setItem('userVertical', pathVertical);
    }
  }, [window.location.pathname, vertical]);

  const config = getVerticalConfig(vertical);
  const theme = getVerticalTheme(vertical);

  return {
    vertical,
    setVertical: (newVertical) => {
      setVertical(newVertical);
      localStorage.setItem('userVertical', newVertical);
      navigate(getVerticalPath(newVertical));
    },
    config,
    theme,
    isFeatureEnabled: (feature) => isFeatureEnabled(vertical, feature),
    navigation: getVerticalNavigation(vertical),
    pathPrefix: getVerticalPath(vertical),
  };
}
