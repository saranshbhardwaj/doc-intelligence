import { Button } from '@/components/ui/button';
import { flattenCitationEntries } from './formatters';

export default function SourceSupportActions({ citations, onOpenSource, title = 'Source support' }) {
  const entries = flattenCitationEntries(citations).slice(0, 3);
  if (entries.length === 0) return null;

  return (
    <div className="mt-4 border-t border-border/60 pt-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">{title}</p>
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {entries.map(({ id, label, title: buttonTitle, entry }) => (
          <Button
            key={id}
            type="button"
            variant="outline"
            size="sm"
            className="h-8 rounded-full px-3 text-xs"
            title={buttonTitle}
            onClick={() => onOpenSource(entry)}
          >
            {label}
          </Button>
        ))}
      </div>
    </div>
  );
}
