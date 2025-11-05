// src/components/dashboard/UsageStats.jsx
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function UsageStats({ userInfo }) {
  const { usage, tier, subscription } = userInfo;
  const isFree = tier === "free";

  // Calculate progress bar percentage
  const progressPercentage = Math.min(usage.percentage_used, 100);

  // Determine color based on usage
  const getProgressColor = () => {
    if (progressPercentage >= 90) return "bg-destructive";
    if (progressPercentage >= 75) return "bg-yellow-500";
    return "bg-primary";
  };

  // Format tier name
  const getTierDisplay = () => {
    return tier.charAt(0).toUpperCase() + tier.slice(1);
  };

  // Format tier badge variant
  const getTierBadgeVariant = () => {
    if (tier === "admin") return "default";
    if (tier === "pro") return "default";
    if (tier === "standard") return "secondary";
    return "outline";
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle>Usage Statistics</CardTitle>
            <CardDescription>
              {isFree
                ? "One-time page limit for free tier"
                : "Monthly page limit resets at the end of billing period"}
            </CardDescription>
          </div>
          <Badge variant={getTierBadgeVariant()}>
            {getTierDisplay()} Tier
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-6">
          {/* Pages Used/Remaining */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium">
                Pages Processed
              </span>
              <span className="text-sm font-medium">
                {usage.pages_used} / {usage.pages_limit}
              </span>
            </div>

            {/* Progress Bar */}
            <div className="w-full bg-muted rounded-full h-2">
              <div
                className={`h-2 rounded-full transition-all duration-300 ${getProgressColor()}`}
                style={{ width: `${progressPercentage}%` }}
              />
            </div>

            <div className="flex items-center justify-between mt-2 text-xs text-muted-foreground">
              <span>
                {usage.pages_remaining} pages remaining
              </span>
              <span>
                {progressPercentage.toFixed(1)}% used
              </span>
            </div>
          </div>

          {/* Warning Messages */}
          {progressPercentage >= 90 && (
            <div className="p-3 bg-destructive/10 border border-destructive/20 rounded-lg text-sm text-destructive">
              <strong>Limit almost reached!</strong> You've used {progressPercentage.toFixed(0)}% of your {isFree ? "one-time" : "monthly"} page limit.
              {isFree && " Upgrade to continue processing documents."}
            </div>
          )}

          {/* Stats Grid */}
          <div className="grid grid-cols-2 gap-4 pt-4 border-t">
            <div>
              <div className="text-xs text-muted-foreground mb-1">
                Total Processed
              </div>
              <div className="text-2xl font-bold">
                {usage.total_pages_processed.toLocaleString()}
              </div>
            </div>

            {!isFree && (
              <div>
                <div className="text-xs text-muted-foreground mb-1">
                  This Month
                </div>
                <div className="text-2xl font-bold">
                  {usage.pages_this_month.toLocaleString()}
                </div>
              </div>
            )}

            {!isFree && subscription.billing_period_end && (
              <div className="col-span-2">
                <div className="text-xs text-muted-foreground mb-1">
                  Billing Period Ends
                </div>
                <div className="text-sm font-medium">
                  {new Date(subscription.billing_period_end).toLocaleDateString(undefined, {
                    year: 'numeric',
                    month: 'long',
                    day: 'numeric'
                  })}
                </div>
              </div>
            )}
          </div>

          {/* Upgrade CTA for free tier */}
          {isFree && progressPercentage >= 75 && (
            <div className="pt-4 border-t">
              <button className="w-full px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors text-sm font-medium">
                Upgrade to Pro
              </button>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
