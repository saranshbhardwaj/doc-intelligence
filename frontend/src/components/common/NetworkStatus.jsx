/**
 * NetworkStatus — global ambient health banner
 *
 * Polls /api/health every 30 seconds. When the server is unreachable, renders
 * an amber banner above the page content so users know why requests are failing
 * or stuck. The banner auto-dismisses when connectivity is restored.
 * Users can also dismiss it manually; dismissal resets on the next new outage.
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "../../api/client";
import { WifiOff } from "lucide-react";

const POLL_INTERVAL_MS = 60_000;
const HEALTH_TIMEOUT_MS = 8_000;

export default function NetworkStatus() {
  const [isDown, setIsDown] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  // Track whether the previous check was already "down" so we know when a
  // new outage starts (and can reset the dismiss state).
  const prevIsDownRef = useRef(false);

  const check = useCallback(async () => {
    try {
      await api.get("/api/health", { timeout: HEALTH_TIMEOUT_MS });
      prevIsDownRef.current = false;
      setIsDown(false);
    } catch {
      if (!prevIsDownRef.current) {
        // New outage — reset dismiss so the banner reappears
        setDismissed(false);
      }
      prevIsDownRef.current = true;
      setIsDown(true);
    }
  }, []);

  useEffect(() => {
    // Delay the first check by 5s so HMR remounts don't cause a request flood.
    // The server must be up if it just served us the page, so this is safe.
    const initial = setTimeout(check, 5_000);
    const id = setInterval(check, POLL_INTERVAL_MS);
    return () => {
      clearTimeout(initial);
      clearInterval(id);
    };
  }, [check]);

  if (!isDown || dismissed) return null;

  return (
    <div
      role="alert"
      className="bg-amber-500/10 border-b border-amber-500/30 px-4 py-2 flex items-center justify-between text-sm text-amber-700 dark:text-amber-400"
    >
      <div className="flex items-center gap-2">
        <WifiOff className="h-4 w-4 shrink-0" />
        <span>Server unreachable — requests may fail or be delayed.</span>
      </div>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        className="ml-4 font-medium text-amber-600 hover:text-amber-800 dark:text-amber-500 dark:hover:text-amber-300 transition-colors"
        aria-label="Dismiss network warning"
      >
        Dismiss
      </button>
    </div>
  );
}
