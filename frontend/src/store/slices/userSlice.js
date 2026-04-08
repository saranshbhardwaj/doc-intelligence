/**
 * User Slice for Zustand Store
 *
 * Manages user information and dashboard data:
 * - User profile and usage stats
 * - Extraction history
 * - Dashboard pagination
 */

import { getUserInfo, getUserExtractions } from '../../api';

export const createUserSlice = (set, get) => ({
  // ========== State ==========
  user: {
    // User info
    info: null,

    // Dashboard data
    extractions: [],
    pagination: {
      total: 0,
      limit: 50,
      offset: 0,
      has_more: false,
    },

    // Loading states
    isLoadingInfo: false,
    isLoadingExtractions: false,
  },

  // ========== Actions ==========

  /**
   * Fetch user info (usage stats, tier, etc.)
   */
  fetchUserInfo: async (getToken) => {
    set((state) => ({
      user: {
        ...state.user,
        isLoadingInfo: true,
      },
    }));

    try {
      const userInfo = await getUserInfo(getToken);
      set((state) => ({
        user: {
          ...state.user,
          info: userInfo,
          isLoadingInfo: false,
        },
      }));
      return userInfo;
    } catch (err) {
      console.error('Failed to fetch user info:', err);
      set((state) => ({
        user: {
          ...state.user,
          isLoadingInfo: false,
        },
      }));
      throw err;
    }
  },

  /**
   * Fetch user's extraction history
   */
  fetchExtractions: async (getToken, options = {}) => {
    set((state) => ({
      user: {
        ...state.user,
        isLoadingExtractions: true,
      },
    }));

    try {
      const { limit = 50, offset = 0 } = options;
      const data = await getUserExtractions(getToken, { limit, offset });

      set((state) => ({
        user: {
          ...state.user,
          extractions: data.extractions,
          pagination: {
            total: data.total,
            limit: data.limit,
            offset: data.offset,
            has_more: data.has_more,
          },
          isLoadingExtractions: false,
        },
      }));

      return data;
    } catch (err) {
      console.error('Failed to fetch extractions:', err);
      set((state) => ({
        user: {
          ...state.user,
          isLoadingExtractions: false,
        },
      }));
      throw err;
    }
  },

  /**
   * Load more extractions (pagination)
   */
  loadMoreExtractions: async (getToken) => {
    const { pagination, extractions } = get().user;

    if (!pagination.has_more) {
      return;
    }

    set((state) => ({
      user: {
        ...state.user,
        isLoadingExtractions: true,
      },
    }));

    try {
      const newOffset = pagination.offset + pagination.limit;
      const data = await getUserExtractions(getToken, {
        limit: pagination.limit,
        offset: newOffset,
      });

      set((state) => ({
        user: {
          ...state.user,
          extractions: [...extractions, ...data.extractions],
          pagination: {
            total: data.total,
            limit: data.limit,
            offset: data.offset,
            has_more: data.has_more,
          },
          isLoadingExtractions: false,
        },
      }));

      return data;
    } catch (err) {
      console.error('Failed to load more extractions:', err);
      set((state) => ({
        user: {
          ...state.user,
          isLoadingExtractions: false,
        },
      }));
      throw err;
    }
  },

  /**
   * Refresh dashboard data (user info + extractions)
   */
  refreshDashboard: async (getToken) => {
    const { fetchUserInfo, fetchExtractions } = get();

    try {
      await Promise.all([
        fetchUserInfo(getToken),
        fetchExtractions(getToken),
      ]);
    } catch (err) {
      console.error('Failed to refresh dashboard:', err);
      throw err;
    }
  },

  /**
   * Clear user data (on sign out)
   */
  clearUserData: () => {
    set({
      user: {
        info: null,
        extractions: [],
        pagination: {
          total: 0,
          limit: 50,
          offset: 0,
          has_more: false,
        },
        isLoadingInfo: false,
        isLoadingExtractions: false,
      },
    });
  },
});
