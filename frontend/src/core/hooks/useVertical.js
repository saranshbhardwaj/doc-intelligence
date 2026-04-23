/**
 * Custom hook for accessing vertical/domain information
 * Gets the current user's vertical from context or URL
 */
import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
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
  const match = pathname.match(/^\/app\/(pe|re)(?:\/|$)/);
  if (!match) return null;
  if (match[1] === 'pe') return 'private_equity';
  if (match[1] === 're') return 'real_estate';
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
  const location = useLocation();
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
    const pathVertical = extractVerticalFromPath(location.pathname);
    if (pathVertical && pathVertical !== vertical) {
      setVertical(pathVertical);
      localStorage.setItem('userVertical', pathVertical);
    }
  }, [location.pathname, vertical]);

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
