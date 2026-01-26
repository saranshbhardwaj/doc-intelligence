/**
 * useExcelWorkbook Hook
 * Encapsulates Excel file loading with caching to avoid reloading on tab switches
 */

import { useState, useEffect } from 'react';
import * as XLSX from 'xlsx';
import { useAuth } from '@clerk/clerk-react';
import { downloadRETemplate } from '../../../api/re-templates';
import { useTemplateFillActions } from '../../../store';

/**
 * Load and cache Excel workbook from template
 *
 * @param {string} templateId - ID of the template to load
 * @returns {Object} { workbook, loading, error }
 */
export function useExcelWorkbook(templateId) {
  const { getToken } = useAuth();
  const { cacheExcelWorkbook, getCachedExcelWorkbook } = useTemplateFillActions();

  const [workbook, setWorkbook] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!templateId) {
      setLoading(false);
      return;
    }

    loadExcelFile();
  }, [templateId]);

  async function loadExcelFile() {
    try {
      setLoading(true);
      setError(null);

      // Check if we have a cached workbook first
      const cached = getCachedExcelWorkbook(templateId);
      if (cached) {
        setWorkbook(cached);
        return;
      }

      // Download and parse Excel file
      const arrayBuffer = await downloadRETemplate(getToken, templateId);

      // Parse with cellFormula and cellStyles to preserve Excel metadata
      const wb = XLSX.read(arrayBuffer, { type: 'array', cellFormula: true, cellStyles: true });

      // Cache the workbook for tab switches
      cacheExcelWorkbook(wb, templateId);
      setWorkbook(wb);
    } catch (err) {
      console.error('❌ Failed to load Excel file:', err);
      setError('Failed to load Excel file');
    } finally {
      setLoading(false);
    }
  }

  return { workbook, loading, error };
}
