/**
 * Enhanced Next Steps Card - Production-quality action items display
 *
 * Features:
 * - Timeline-style layout with connecting lines
 * - Priority badges with color coding
 * - Owner and timeline information
 * - Visual progression indicators
 * - Hover effects
 */

import { CheckSquare, Clock, User, ArrowRight } from "lucide-react";
import { Card } from "../ui/card";
import { Badge } from "../ui/badge";

export default function NextStepsCard({ nextSteps }) {
  if (!nextSteps || nextSteps.length === 0) return null;

  // Sort by priority
  const sorted = [...nextSteps].sort(
    (a, b) => (a.priority || 99) - (b.priority || 99)
  );

  const getPriorityColor = (priority) => {
    if (priority === 1) return "bg-destructive text-destructive-foreground";
    if (priority === 2) return "bg-warning text-foreground";
    if (priority === 3) return "bg-warning text-foreground";
    return "bg-primary text-primary-foreground";
  };

  const getTimelineUrgency = (days) => {
    if (!days) return "default";
    if (days <= 7) return "urgent";
    if (days <= 14) return "moderate";
    return "normal";
  };

  const urgencyColors = {
    urgent: "text-destructive",
    moderate: "text-warning",
    normal: "text-primary",
    default: "text-muted-foreground"
  };

  return (
    <Card className="rounded-xl shadow-lg overflow-hidden border-l-4 border-primary">
      {/* Header */}
      <div className="px-6 py-4 bg-gradient-to-r from-primary/5 to-primary/10 dark:from-primary/10 dark:to-primary/20 border-b border-border">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-primary/10 rounded-lg">
            <CheckSquare className="w-6 h-6 text-primary" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-foreground">Recommended Next Steps</h2>
            <p className="text-sm text-muted-foreground">Action items for deal progression</p>
          </div>
        </div>
      </div>

      <div className="p-6">
        {/* Timeline */}
        <div className="space-y-4">
          {sorted.map((step, idx) => {
            const urgency = getTimelineUrgency(step.timeline_days);
            const isLastStep = idx === sorted.length - 1;

            return (
              <div key={idx} className="relative">
                {/* Connector Line */}
                {!isLastStep && (
                  <div className="absolute left-5 top-12 bottom-0 w-0.5 bg-gradient-to-b from-primary/30 to-primary/10" />
                )}

                <div className="flex items-start gap-4 group hover:translate-x-1 transition-transform duration-200">
                  {/* Priority Circle */}
                  <div
                    className={`flex-shrink-0 w-10 h-10 ${getPriorityColor(
                      step.priority
                    )} rounded-full flex items-center justify-center font-bold text-sm shadow-md z-10 group-hover:scale-110 transition-transform`}
                  >
                    {step.priority || idx + 1}
                  </div>

                  {/* Content Card */}
                  <div className="flex-1 bg-card rounded-lg border border-border p-4 shadow-sm group-hover:shadow-md transition-shadow">
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex-1">
                        <p className="font-semibold text-foreground mb-2 leading-snug">
                          {step.action}
                        </p>

                        {/* Metadata */}
                        <div className="flex items-center gap-4 text-sm flex-wrap">
                          {/* Owner */}
                          {step.owner && (
                            <div className="flex items-center gap-1.5 text-muted-foreground">
                              <User className="w-3.5 h-3.5" />
                              <span className="font-medium">{step.owner}</span>
                            </div>
                          )}

                          {/* Timeline */}
                          {step.timeline_days && (
                            <div className={`flex items-center gap-1.5 ${urgencyColors[urgency]}`}>
                              <Clock className="w-3.5 h-3.5" />
                              <span className="font-medium">
                                {step.timeline_days} days
                              </span>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Arrow Indicator */}
                      {!isLastStep && (
                        <ArrowRight className="w-5 h-5 text-muted-foreground flex-shrink-0 mt-1 opacity-0 group-hover:opacity-100 transition-opacity" />
                      )}
                    </div>

                    {/* Priority Badge */}
                    {step.priority && step.priority <= 2 && (
                      <div className="mt-3">
                        <Badge variant="destructive" className="text-xs">
                          High Priority
                        </Badge>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </Card>
  );
}
