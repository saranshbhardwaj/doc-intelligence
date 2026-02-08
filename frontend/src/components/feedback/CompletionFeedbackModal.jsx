/**
 * CompletionFeedbackModal Component
 *
 * Non-blocking modal for collecting feedback on completed operations
 * (workflows, template fills, extractions).
 *
 * Features:
 * - 5-star rating system
 * - Category chips for low ratings (accuracy, speed, format, missing_data)
 * - Optional comment field
 * - Non-blocking: User can dismiss by clicking outside or Skip button
 *
 * Props:
 *   - isOpen: Modal open state
 *   - onClose: Callback when modal closes
 *   - operationType: "workflow" | "template_fill" | "extraction"
 *   - entityId: ID of the workflow run, template fill run, or extraction
 *   - entitySummary: Optional display name/summary for context
 *   - onFeedbackSubmitted: Optional callback when feedback is successfully submitted
 */

import { useState } from "react";
import { Star, MessageSquare } from "lucide-react";
import { Button } from "../ui/button";
import { Textarea } from "../ui/textarea";
import { Badge } from "../ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "../ui/dialog";
import { cn } from "@/lib/utils";
import { submitFeedback } from "../../api/feedback";
import { useUser } from "../../store";
import { toast } from "sonner";

const OPERATION_TYPE_LABELS = {
  workflow: "workflow run",
  template_fill: "template fill",
  extraction: "extraction",
};

const FEEDBACK_CATEGORIES = [
  { value: "accuracy", label: "Accuracy" },
  { value: "speed", label: "Speed" },
  { value: "format", label: "Format" },
  { value: "missing_data", label: "Missing Data" },
];

export default function CompletionFeedbackModal({
  isOpen,
  onClose,
  operationType,
  entityId,
  entitySummary,
  onFeedbackSubmitted,
}) {
  const [rating, setRating] = useState(0);
  const [hoveredRating, setHoveredRating] = useState(0);
  const [category, setCategory] = useState(null);
  const [comment, setComment] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const { getToken } = useUser();

  const operationLabel = OPERATION_TYPE_LABELS[operationType] || operationType;

  const handleReset = () => {
    setRating(0);
    setHoveredRating(0);
    setCategory(null);
    setComment("");
    setIsSubmitting(false);
  };

  const handleClose = () => {
    handleReset();
    onClose();
  };

  const handleSubmit = async () => {
    if (rating === 0) {
      toast.error("Please select a rating");
      return;
    }

    setIsSubmitting(true);

    try {
      const token = await getToken();

      // Build entity ID field based on operation type
      const entityIdField = {};
      if (operationType === "workflow") {
        entityIdField.workflow_run_id = entityId;
      } else if (operationType === "template_fill") {
        entityIdField.template_fill_run_id = entityId;
      } else if (operationType === "extraction") {
        entityIdField.extraction_id = entityId;
      }

      const response = await submitFeedback(token, {
        ...entityIdField,
        rating_type: "stars",
        rating_value: rating,
        comment: comment || undefined,
        feedback_category: category || undefined,
        context_snapshot: {
          entity_summary: entitySummary,
        },
      });

      toast.success(response.message || "Thank you for your feedback!");

      // Notify parent component
      if (onFeedbackSubmitted) {
        onFeedbackSubmitted(response.feedback_id);
      }

      handleClose();
    } catch (error) {
      console.error("Failed to submit feedback:", error);
      toast.error(error.response?.data?.detail || "Failed to submit feedback");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && handleClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>How was this {operationLabel}?</DialogTitle>
          <DialogDescription className="text-muted-foreground text-sm">
            {entitySummary && <span className="font-medium">{entitySummary}</span>}
            {entitySummary && <br />}
            Optional - your feedback helps us improve
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-4">
          {/* Star Rating */}
          <div className="flex justify-center gap-2">
            {[1, 2, 3, 4, 5].map((starValue) => {
              const isFilled = starValue <= (hoveredRating || rating);
              return (
                <button
                  key={starValue}
                  type="button"
                  onClick={() => setRating(starValue)}
                  onMouseEnter={() => setHoveredRating(starValue)}
                  onMouseLeave={() => setHoveredRating(0)}
                  className="transition-transform hover:scale-110 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 rounded"
                  disabled={isSubmitting}
                  aria-label={`${starValue} star${starValue !== 1 ? 's' : ''}`}
                >
                  <Star
                    className={cn(
                      "w-8 h-8 transition-colors",
                      isFilled
                        ? "fill-yellow-400 text-yellow-400"
                        : "text-muted-foreground"
                    )}
                  />
                </button>
              );
            })}
          </div>

          {/* Category chips for low ratings */}
          {rating > 0 && rating <= 3 && (
            <div className="space-y-2">
              <p className="text-sm text-muted-foreground">
                What could be improved?
              </p>
              <div className="flex gap-2 flex-wrap justify-center">
                {FEEDBACK_CATEGORIES.map((cat) => (
                  <Badge
                    key={cat.value}
                    variant={category === cat.value ? "default" : "outline"}
                    className="cursor-pointer transition-colors"
                    onClick={() =>
                      setCategory(category === cat.value ? null : cat.value)
                    }
                  >
                    {cat.label}
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Optional comment */}
          {rating > 0 && (
            <div className="space-y-2">
              <label htmlFor="feedback-comment" className="text-sm font-medium">
                Additional feedback (optional)
              </label>
              <Textarea
                id="feedback-comment"
                placeholder={
                  rating <= 3
                    ? "Tell us what went wrong..."
                    : "Tell us what you loved!"
                }
                value={comment}
                onChange={(e) => setComment(e.target.value)}
                className="min-h-[80px] text-sm"
                maxLength={500}
                disabled={isSubmitting}
              />
              <p className="text-xs text-muted-foreground text-right">
                {comment.length}/500
              </p>
            </div>
          )}
        </div>

        <DialogFooter className="gap-2 sm:gap-0">
          <Button variant="ghost" onClick={handleClose} disabled={isSubmitting}>
            Skip
          </Button>
          <Button onClick={handleSubmit} disabled={rating === 0 || isSubmitting}>
            {isSubmitting ? "Submitting..." : "Submit Feedback"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
