/**
 * FeedbackButton Component
 *
 * Manual feedback trigger button for workflows, template fills, and extractions.
 * Always visible in result views. Shows "Feedback submitted" if already given.
 *
 * Props:
 *   - operationType: "workflow" | "template_fill" | "extraction"
 *   - entityId: ID of the workflow run, template fill run, or extraction
 *   - entitySummary: Optional display name/summary for context
 *   - variant: Button variant (default: "outline")
 *   - size: Button size (default: "sm")
 */

import { useState, useEffect } from "react";
import { MessageSquare, CheckCircle } from "lucide-react";
import { Button } from "../ui/button";
import CompletionFeedbackModal from "./CompletionFeedbackModal";

export default function FeedbackButton({
  operationType,
  entityId,
  entitySummary,
  variant = "outline",
  size = "sm",
}) {
  const [showModal, setShowModal] = useState(false);
  const [feedbackSubmitted, setFeedbackSubmitted] = useState(false);

  // Check localStorage for existing feedback
  useEffect(() => {
    if (!entityId) return;

    const feedbackKey = `feedback_submitted_${operationType}_${entityId}`;
    const hasSubmitted = localStorage.getItem(feedbackKey) === "true";
    setFeedbackSubmitted(hasSubmitted);
  }, [operationType, entityId]);

  const handleFeedbackSubmitted = () => {
    // Mark as submitted in localStorage
    const feedbackKey = `feedback_submitted_${operationType}_${entityId}`;
    localStorage.setItem(feedbackKey, "true");
    setFeedbackSubmitted(true);
    setShowModal(false);
  };

  if (feedbackSubmitted) {
    return (
      <div className="flex items-center gap-1.5 text-sm text-muted-foreground">
        <CheckCircle className="w-4 h-4 text-success" />
        <span>Feedback submitted</span>
      </div>
    );
  }

  return (
    <>
      <Button variant={variant} size={size} onClick={() => setShowModal(true)}>
        <MessageSquare className="w-4 h-4 mr-1.5" />
        Give Feedback
      </Button>
      <CompletionFeedbackModal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        operationType={operationType}
        entityId={entityId}
        entitySummary={entitySummary}
        onFeedbackSubmitted={handleFeedbackSubmitted}
      />
    </>
  );
}
