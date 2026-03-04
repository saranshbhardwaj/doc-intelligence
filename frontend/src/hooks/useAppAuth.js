/**
 * useAppAuth — thin wrapper around WorkOS AuthKit's useAuth()
 *
 * Exposes the same interface that components previously used from Clerk's
 * useAuth(), so every call site only needs an import swap:
 *   import { useAuth } from '@clerk/clerk-react'  →  import { useAppAuth } from '../hooks/useAppAuth'
 *   useAuth()                                      →  useAppAuth()
 */
import { useAuth } from "@workos-inc/authkit-react";

export function useAppAuth() {
  const { user, isLoading, getAccessToken, signOut, organizationId } = useAuth();
  return {
    isLoaded: !isLoading,
    isSignedIn: !!user,
    userId: user?.id ?? null,
    orgId: organizationId ?? null,
    // getToken() mirrors Clerk's interface — returns a Promise<string | null>
    getToken: getAccessToken,
    signOut,
    user,
  };
}
