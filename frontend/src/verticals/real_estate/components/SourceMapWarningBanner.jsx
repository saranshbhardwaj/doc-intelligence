import React, { useState } from 'react';
import { AlertCircle, X } from 'lucide-react';
import { Alert, AlertDescription } from '../../../components/ui/alert';
import { Button } from '../../../components/ui/button';
import { cn } from '@/lib/utils';

export default function SourceMapWarningBanner({ summary, onReview }) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;

  const lowKeys = summary?.low_confidence_keys ?? [];
  const keyList = lowKeys.slice(0, 3).map(k =>
    k.replace(/^(column_map|section_presence)\./, '').replace(/_/g, ' ')
  );
  const extraCount = lowKeys.length - keyList.length;

  return (
    <Alert
      variant="default"
      className={cn(
        'border-warning/30 bg-warning/10',
        'flex items-start gap-2 py-2 px-3',
      )}
    >
      <AlertCircle className="h-3.5 w-3.5 text-warning shrink-0 mt-0.5" />
      <AlertDescription className="flex-1 text-xs text-foreground leading-snug">
        <span className="font-medium">Low-confidence structure detected</span>
        {keyList.length > 0 && (
          <span className="text-muted-foreground">
            {' '}— {keyList.join(', ')}{extraCount > 0 ? ` +${extraCount} more` : ''}
          </span>
        )}
        . Filled cells that depend on these may be unreliable.{' '}
        <button
          type="button"
          onClick={onReview}
          className="underline underline-offset-2 hover:no-underline font-medium cursor-pointer"
        >
          Review structure
        </button>
      </AlertDescription>
      <Button
        variant="ghost"
        size="sm"
        className="h-5 w-5 p-0 text-muted-foreground hover:text-foreground hover:bg-muted/50 shrink-0"
        onClick={() => setDismissed(true)}
      >
        <X className="h-3 w-3" />
      </Button>
    </Alert>
  );
}
