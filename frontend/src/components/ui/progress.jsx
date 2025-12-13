import * as React from "react";
import * as ProgressPrimitive from "@radix-ui/react-progress";

function cn(...classes) {
  return classes.filter(Boolean).join(" ");
}

/**
 * Progress component (Radix based) - ChatGPT-inspired with shimmer effect
 * Usage: <Progress value={percent} variant="primary" showShimmer />
 *
 * Variants: primary (default), success, warning, destructive
 */
export const Progress = React.forwardRef(
  ({ className, value = 0, variant = "primary", showShimmer = false, ...props }, ref) => {
    const clamped = Math.min(100, Math.max(0, value));

    // Variant colors using theme tokens only
    const variantStyles = {
      primary: "bg-primary",
      success: "bg-success",
      warning: "bg-warning",
      destructive: "bg-destructive",
    };

    const indicatorColor = variantStyles[variant] || variantStyles.primary;

    return (
      <ProgressPrimitive.Root
        ref={ref}
        className={cn(
          "relative h-2 w-full overflow-hidden rounded-full bg-muted",
          className
        )}
        value={clamped}
        {...props}
      >
        <ProgressPrimitive.Indicator
          className={cn(
            "h-full w-full transition-all duration-500 ease-out relative",
            indicatorColor,
            showShimmer && "overflow-hidden"
          )}
          style={{ transform: `translateX(-${100 - clamped}%)` }}
        >
          {showShimmer && (
            <div
              className="absolute inset-0 w-full h-full opacity-40"
              style={{
                background: 'linear-gradient(90deg, transparent 0%, rgba(255, 255, 255, 0.6) 50%, transparent 100%)',
                animation: 'shimmer 2s ease-in-out infinite',
              }}
            />
          )}
        </ProgressPrimitive.Indicator>

        {showShimmer && (
          <style>
            {`
              @keyframes shimmer {
                0% {
                  transform: translateX(-100%);
                }
                100% {
                  transform: translateX(100%);
                }
              }
            `}
          </style>
        )}
      </ProgressPrimitive.Root>
    );
  }
);
Progress.displayName = "Progress";
