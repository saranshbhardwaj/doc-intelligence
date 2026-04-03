/**
 * NetworkStatus — global ambient health banner
 *
 * Polls /api/health periodically and shows a conservative connectivity signal.
 *
 * Behavior:
 * - Uses consecutive failures to avoid transient false alarms
 * - Shows "degraded" first during heavy backend load
 * - Escalates to "unreachable" only after sustained failures with no active jobs
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { api } from "../../api/client";
import { WifiOff } from "lucide-react";
import { useStore } from "../../store";

const POLL_INTERVAL_MS = 60_000;
const HEALTH_TIMEOUT_MS = 15_000;
const FAILURES_FOR_DEGRADED = 2;
const FAILURES_FOR_UNREACHABLE = 4;

export default function NetworkStatus() {
  const [status, setStatus] = useState("healthy"); // healthy | degraded | down
  const [dismissed, setDismissed] = useState(false);
  const failureCountRef = useRef(0);
  const previousStatusRef = useRef("healthy");

  const hasActiveIndexingJobs = useStore((state) =>
    Object.values(state.chat?.indexingJobs || {}).some((job) => job?.isProcessing)
  );

  const check = useCallback(async () => {
    try {
      await api.get("/api/health", { timeout: HEALTH_TIMEOUT_MS });
      failureCountRef.current = 0;
      previousStatusRef.current = "healthy";
      setStatus("healthy");
    } catch {
      failureCountRef.current += 1;

      let nextStatus = "healthy";
      if (failureCountRef.current >= FAILURES_FOR_DEGRADED) {
        nextStatus = "degraded";
      }
      if (
        failureCountRef.current >= FAILURES_FOR_UNREACHABLE &&
        !hasActiveIndexingJobs
      ) {
        nextStatus = "down";
      }

      if (previousStatusRef.current === "healthy" && nextStatus !== "healthy") {
        // New incident window — re-show banner even if user dismissed previous one.
        setDismissed(false);
      }

      previousStatusRef.current = nextStatus;
      setStatus(nextStatus);
    }
  }, [hasActiveIndexingJobs]);

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

  if (status === "healthy" || dismissed) return null;

  const isDown = status === "down";
  const bannerText = isDown
    ? "Server appears unreachable — requests may fail."
    : "Server is busy or slow — requests may be delayed.";
  const bannerClasses = isDown
    ? "bg-destructive/10 border-b border-destructive/30 text-destructive"
    : "bg-amber-500/10 border-b border-amber-500/30 text-amber-700 dark:text-amber-400";
  const buttonClasses = isDown
    ? "text-destructive hover:text-destructive/80"
    : "text-amber-600 hover:text-amber-800 dark:text-amber-500 dark:hover:text-amber-300";

  return (
    <div
      role="alert"
      className={`px-4 py-2 flex items-center justify-between text-sm ${bannerClasses}`}
    >
      <div className="flex items-center gap-2">
        <WifiOff className="h-4 w-4 shrink-0" />
        <span>{bannerText}</span>
      </div>
      <button
        type="button"
        onClick={() => setDismissed(true)}
        className={`ml-4 font-medium transition-colors ${buttonClasses}`}
        aria-label="Dismiss network warning"
      >
        Dismiss
      </button>
    </div>
  );
}
