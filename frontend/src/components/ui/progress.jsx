import * as React from 'react';
import * as ProgressPrimitive from '@radix-ui/react-progress';

// Optional utility; fall back if not present
function cn(...classes) {
  return classes.filter(Boolean).join(' ');
}

/**
 * Progress component (Radix based)
 * Usage: <Progress value={percent} />
 */
export const Progress = React.forwardRef(({ className, value = 0, ...props }, ref) => {
  const clamped = Math.min(100, Math.max(0, value));
  return (
    <ProgressPrimitive.Root
      ref={ref}
      className={cn(
        'relative h-2 w-full overflow-hidden rounded bg-muted dark:bg-neutral-800',
        className
      )}
      value={clamped}
      {...props}
    >
      <ProgressPrimitive.Indicator
        className={cn(
          'h-full w-full bg-indigo-600 dark:bg-indigo-400 transition-transform duration-300 ease-out'
        )}
        style={{ transform: `translateX(-${100 - clamped}%)` }}
      />
    </ProgressPrimitive.Root>
  );
});
Progress.displayName = 'Progress';
