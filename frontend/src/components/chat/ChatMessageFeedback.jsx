/**
 * ChatMessageFeedback Component
 *
 * Inline thumbs up/down feedback for chat messages (ChatGPT-style).
 * Appears below each assistant message with minimal, hover-activated UI.
 *
 * Props:
 *   - messageId: Chat message ID to submit feedback for
 *   - sessionId: Current chat session ID
 *   - onFeedbackSubmitted: Optional callback when feedback is submitted
 */

import { useState } from "react";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import { Button } from "../ui/button";
import { Textarea } from "../ui/textarea";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { cn } from "@/lib/utils";
import { submitFeedback } from "../../api/feedback";
import { useUser } from "../../store";
import { toast } from "sonner";

export default function ChatMessageFeedback({ messageId, sessionId, onFeedbackSubmitted }) {
  const [feedback, setFeedback] = useState(null); // 1 or -1
  const [comment, setComment] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showCommentPopover, setShowCommentPopover] = useState(false);
  const { getToken } = useUser();

  const handleThumbsClick = async (value) => {
    if (feedback === value) {
      // Already submitted this feedback
      return;
    }

    // For thumbs down, show comment popover
    if (value === -1) {
      setFeedback(value);
      setShowCommentPopover(true);
      return;
    }

    // For thumbs up, submit immediately
    await submitThumbsFeedback(value, "");
  };

  const submitThumbsFeedback = async (ratingValue, commentText) => {
    setIsSubmitting(true);

    try {
      const token = await getToken();
      const response = await submitFeedback(token, {
        chat_message_id: messageId,
        rating_type: "thumbs",
        rating_value: ratingValue,
        comment: commentText || undefined,
        context_snapshot: {
          session_id: sessionId,
        },
      });

      setFeedback(ratingValue);
      setShowCommentPopover(false);

      toast.success(response.message || "Thank you for your feedback!");

      if (onFeedbackSubmitted) {
        onFeedbackSubmitted(response.feedback_id);
      }
    } catch (error) {
      console.error("Failed to submit feedback:", error);
      toast.error(error.response?.data?.detail || "Failed to submit feedback");
      setFeedback(null); // Reset on error
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCommentSubmit = async () => {
    if (!feedback) return;
    await submitThumbsFeedback(feedback, comment);
  };

  return (
    <div className="flex items-center gap-1 mt-2 opacity-0 group-hover:opacity-60 hover:opacity-100 transition-opacity duration-200">
      {/* Thumbs Up */}
      <Button
        variant="ghost"
        size="icon"
        className="h-6 w-6"
        onClick={() => handleThumbsClick(1)}
        disabled={isSubmitting || feedback === -1}
        title="Good response"
      >
        <ThumbsUp
          className={cn(
            "h-3.5 w-3.5",
            feedback === 1 ? "text-success fill-success" : "text-muted-foreground"
          )}
        />
      </Button>

      {/* Thumbs Down with Comment Popover */}
      <Popover open={showCommentPopover} onOpenChange={setShowCommentPopover}>
        <PopoverTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            onClick={() => handleThumbsClick(-1)}
            disabled={isSubmitting || feedback === 1}
            title="Bad response"
          >
            <ThumbsDown
              className={cn(
                "h-3.5 w-3.5",
                feedback === -1 ? "text-destructive fill-destructive" : "text-muted-foreground"
              )}
            />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-80" align="start">
          <div className="space-y-3">
            <div>
              <h4 className="text-sm font-semibold mb-1">What went wrong?</h4>
              <p className="text-xs text-muted-foreground">
                Optional: Help us improve by describing the issue
              </p>
            </div>
            <Textarea
              placeholder="The response was inaccurate, unhelpful, or..."
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              className="min-h-[80px] text-sm"
              maxLength={500}
            />
            <div className="flex gap-2 justify-end">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setShowCommentPopover(false);
                  setFeedback(null);
                  setComment("");
                }}
              >
                Cancel
              </Button>
              <Button
                size="sm"
                onClick={handleCommentSubmit}
                disabled={isSubmitting}
              >
                {isSubmitting ? "Submitting..." : "Submit"}
              </Button>
            </div>
          </div>
        </PopoverContent>
      </Popover>
    </div>
  );
}
