import { useAppAuth } from "@/hooks/useAppAuth";
import { Clock, LogOut } from "lucide-react";

export default function AccessPendingPage() {
  const { signOut } = useAppAuth();

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-background">
      <div className="max-w-md w-full mx-4 rounded-lg border border-border bg-card p-8 shadow-sm text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-900/30">
          <Clock className="h-6 w-6 text-amber-600 dark:text-amber-400" />
        </div>
        <h2 className="mb-2 text-xl font-semibold text-foreground">
          Access Pending
        </h2>
        <p className="mb-6 text-sm text-muted-foreground">
          Your account is awaiting approval. We'll notify you by email once
          your access has been activated.
        </p>
        <button
          onClick={() => signOut?.()}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          <LogOut className="h-4 w-4" />
          Sign Out
        </button>
      </div>
    </div>
  );
}
