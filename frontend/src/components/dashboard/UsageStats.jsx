// src/components/dashboard/UsageStats.jsx
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FileSpreadsheet, MessageSquare } from "lucide-react";

function UsageBar({ used, limit, window: resetWindow }) {
  if (!limit) return (
    <p className="text-xs text-muted-foreground">Unlimited</p>
  );

  const pct = Math.min((used / limit) * 100, 100);
  const barColor = pct >= 90 ? "bg-destructive" : pct >= 80 ? "bg-yellow-500" : "bg-primary";
  const resetLabel = resetWindow === "monthly" ? "Resets on the 1st of each month" : "Resets at midnight UTC";

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium">{used} / {limit}</span>
        <span className="text-xs text-muted-foreground">{pct.toFixed(0)}% used</span>
      </div>
      <div className="w-full bg-muted rounded-full h-2">
        <div
          className={`h-2 rounded-full transition-all duration-300 ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-muted-foreground">{resetLabel}</p>
      {pct >= 90 && (
        <div className="p-2 bg-destructive/10 border border-destructive/20 rounded text-xs text-destructive">
          Limit almost reached — {resetLabel.toLowerCase()}.
        </div>
      )}
    </div>
  );
}

export default function UsageStats({ userInfo }) {
  const { tier, limits } = userInfo;
  const fills = limits?.template_fill_runs;
  const chats = limits?.chat_messages;

  const getTierDisplay = () => tier.charAt(0).toUpperCase() + tier.slice(1);
  const getTierBadgeVariant = () => {
    if (tier === "admin" || tier === "pro") return "default";
    if (tier === "standard") return "secondary";
    return "outline";
  };

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <CardTitle>Usage Statistics</CardTitle>
            <CardDescription>Your monthly fills and daily chat activity</CardDescription>
          </div>
          <Badge variant={getTierBadgeVariant()} className="w-fit">
            {getTierDisplay()} Tier
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          {/* Template Fill Runs */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <FileSpreadsheet className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-medium">Template Fills This Month</span>
            </div>
            {fills ? (
              <UsageBar used={fills.used} limit={fills.limit} window={fills.window} />
            ) : (
              <p className="text-xs text-muted-foreground">No data</p>
            )}
          </div>

          {/* Chat Messages */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-muted-foreground" />
              <span className="text-sm font-medium">Chat Messages Today</span>
            </div>
            {chats ? (
              <UsageBar used={chats.used} limit={chats.limit} window={chats.window} />
            ) : (
              <p className="text-xs text-muted-foreground">No data</p>
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
