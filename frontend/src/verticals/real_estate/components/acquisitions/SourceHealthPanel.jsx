import { Cloud, Database, Mail, RefreshCw, UploadCloud, X } from 'lucide-react';
import { labelFromSnake } from '../../utils/acquisitionWorkspace';

const ICONS = {
  gmail: Mail,
  outlook: Mail,
  public_api: Cloud,
  private_api: Database,
  manual_upload: UploadCloud,
};

export default function SourceHealthPanel({ connectors, open, onClose }) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 bg-background/80 backdrop-blur-sm">
      <div className="absolute inset-x-4 top-8 mx-auto max-w-3xl rounded-lg border border-border bg-card shadow-xl">
        <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
          <div>
            <h2 className="text-lg font-semibold text-foreground">Source Status</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Connector-ready sources for future deal ingestion. Sync and configuration controls are preview-only.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
            aria-label="Close source status"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        <div className="grid max-h-[75vh] gap-3 overflow-y-auto p-4 md:grid-cols-2">
          {connectors.map((connector) => {
            const Icon = ICONS[connector.type] || Database;
            return (
              <div key={connector.id} className="rounded-md border border-border/70 bg-background/70 p-3">
                <div className="flex items-start gap-2">
                  <Icon className="mt-0.5 h-4 w-4 text-muted-foreground" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <p className="text-sm font-semibold text-foreground">{connector.name}</p>
                      <span className="rounded-full border border-border/70 px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                        {labelFromSnake(connector.status)}
                      </span>
                    </div>
                    <p className="mt-1 text-xs leading-5 text-muted-foreground">{connector.description}</p>
                    <div className="mt-2 grid gap-1 text-[11px] text-muted-foreground">
                      <div className="flex justify-between gap-3">
                        <span>Cost model</span>
                        <span className="font-medium text-foreground">{labelFromSnake(connector.costModel)}</span>
                      </div>
                      <div className="flex justify-between gap-3">
                        <span>Mock candidates</span>
                        <span className="font-medium text-foreground">{connector.candidatesFound || 0}</span>
                      </div>
                      <div className="flex justify-between gap-3">
                        <span>Sync mode</span>
                        <span className="font-medium text-foreground">Manual preview</span>
                      </div>
                    </div>
                    <button
                      type="button"
                      disabled
                      className="mt-3 inline-flex items-center gap-1.5 rounded-md border border-border bg-muted/50 px-2.5 py-1.5 text-xs font-medium text-muted-foreground opacity-75"
                    >
                      <RefreshCw className="h-3.5 w-3.5" /> Sync coming soon
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
        <div className="flex justify-end border-t border-border px-4 py-3">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-border bg-background px-3 py-2 text-sm font-medium text-muted-foreground"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}