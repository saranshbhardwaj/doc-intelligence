/**
 * useAppAuth — thin wrapper around WorkOS AuthKit's useAuth()
 *
 * Exposes the same interface that components previously used from Clerk's
 * useAuth(), so every call site only needs an import swap:
 *   import { useAuth } from '@clerk/clerk-react'  →  import { useAppAuth } from '../hooks/useAppAuth'
 *   useAuth()                                      →  useAppAuth()
 */
import { useCallback, useEffect } from "react";
import { useAuth } from "@workos-inc/authkit-react";
import { usePostHog } from "@posthog/react";

export function useAppAuth() {
  const { user, isLoading, getAccessToken, signOut, organizationId } = useAuth();
  const posthog = usePostHog();

  // Stabilize getToken so it doesn't change on every render.
  // Without this, any useCallback/useEffect depending on getToken would
  // re-run on every render, causing infinite fetch/SSE loops.
  const getToken = useCallback(
    (...args) => getAccessToken(...args),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [], // intentionally empty: getAccessToken identity is stable from WorkOS SDK
  );

  // Identify the user in PostHog once WorkOS resolves the user
  useEffect(() => {
    if (user?.id) {
      posthog?.identify(user.id, {
        email: user.email,
      });
    }
  }, [posthog, user?.id, user?.email]);

  return {
    isLoaded: !isLoading,
    isSignedIn: !!user,
    userId: user?.id ?? null,
    orgId: organizationId ?? null,
    // getToken() mirrors Clerk's interface — returns a Promise<string | null>
    getToken,
    signOut,
    user,
  };
}
