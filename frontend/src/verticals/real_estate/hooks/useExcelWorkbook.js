/**
 * useExcelWorkbook Hook
 * Encapsulates Excel file loading with caching to avoid reloading on tab switches
 */

import { useState, useEffect } from 'react';
import * as XLSX from 'xlsx';
import { useAppAuth } from "@/hooks/useAppAuth";
import { downloadRETemplate } from '../../../api/re-templates';
import { useTemplateFillActions } from '../../../store';

/**
 * Load and cache Excel workbook from template
 *
 * @param {string} templateId - ID of the template to load
 * @returns {Object} { workbook, loading, error }
 */
export function useExcelWorkbook(templateId) {
  const { getToken } = useAppAuth();
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

      // Download Excel file
      const arrayBuffer = await downloadRETemplate(getToken, templateId);

      // Parse off the current call stack so the browser can paint the loading spinner
      // before the synchronous XLSX.read blocks the main thread (can take 1-3s with cellStyles).
      await new Promise((resolve, reject) => {
        setTimeout(() => {
          try {
            // Parse with cellFormula and cellStyles to preserve Excel metadata
            const wb = XLSX.read(arrayBuffer, { type: 'array', cellFormula: true, cellStyles: true });
            cacheExcelWorkbook(wb, templateId);
            setWorkbook(wb);
            resolve();
          } catch (err) {
            reject(err);
          }
        }, 0);
      });
    } catch (err) {
      console.error('❌ Failed to load Excel file:', err);
      setError('Failed to load Excel file');
    } finally {
      setLoading(false);
    }
  }

  return { workbook, loading, error };
}
