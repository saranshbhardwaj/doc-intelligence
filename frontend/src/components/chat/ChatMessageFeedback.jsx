/**
 * ChatMessageFeedback Component
 *
 * Inline thumbs up/down feedback for chat messages (ChatGPT-style).
 * Appears below each assistant message with minimal, hover-activated UI.
 *
 * Behavior:
 *   - Click thumb: submit feedback (upsert)
 *   - Click same thumb again: toggle off (delete)
 *   - Click other thumb: switch (upsert with new value)
 *   - State persists across page refreshes via initialFeedback prop
 *
 * Props:
 *   - messageId: Chat message ID to submit feedback for
 *   - sessionId: Current chat session ID
 *   - initialFeedback: { rating_value, feedback_id, comment } from API (or null)
 */

import { useState, useEffect } from "react";
import { ThumbsUp, ThumbsDown } from "lucide-react";
import { Button } from "../ui/button";
import { Textarea } from "../ui/textarea";
import { Popover, PopoverContent, PopoverTrigger } from "../ui/popover";
import { cn } from "@/lib/utils";
import { submitFeedback, deleteChatFeedback } from "../../api/feedback";
import { useAuth } from "@clerk/clerk-react";
import { toast } from "sonner";

export default function ChatMessageFeedback({ messageId, sessionId, initialFeedback }) {
  const [feedback, setFeedback] = useState(initialFeedback?.rating_value ?? null);
  const [comment, setComment] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showCommentPopover, setShowCommentPopover] = useState(false);
  const { getToken } = useAuth();

  // Sync with initialFeedback when it changes (e.g. after message refresh)
  useEffect(() => {
    setFeedback(initialFeedback?.rating_value ?? null);
  }, [initialFeedback?.rating_value]);

  const handleThumbsClick = async (value) => {
    if (isSubmitting) return;

    // Toggle off: clicking the same thumb removes feedback
    if (feedback === value) {
      await removeFeedback();
      return;
    }

    // Thumbs down: show comment popover before submitting
    if (value === -1) {
      setShowCommentPopover(true);
      return;
    }

    // Thumbs up: submit immediately (upsert)
    await upsertFeedback(value, "");
  };

  const upsertFeedback = async (ratingValue, commentText) => {
    setIsSubmitting(true);
    try {
      await submitFeedback(getToken, {
        chat_message_id: messageId,
        rating_type: "thumbs",
        rating_value: ratingValue,
        comment: commentText || undefined,
        context_snapshot: { session_id: sessionId },
      });
      setFeedback(ratingValue);
      setShowCommentPopover(false);
      setComment("");
    } catch (error) {
      console.error("Failed to submit feedback:", error);
      toast.error(error.response?.data?.detail || "Failed to submit feedback");
    } finally {
      setIsSubmitting(false);
    }
  };

  const removeFeedback = async () => {
    setIsSubmitting(true);
    try {
      await deleteChatFeedback(getToken, messageId);
      setFeedback(null);
      setComment("");
    } catch (error) {
      console.error("Failed to remove feedback:", error);
      toast.error("Failed to remove feedback");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCommentSubmit = async () => {
    await upsertFeedback(-1, comment);
  };

  return (
    <div className="flex items-center gap-1 mt-2 opacity-0 group-hover:opacity-60 hover:opacity-100 transition-opacity duration-200">
      {/* Thumbs Up */}
      <Button
        variant="ghost"
        size="icon"
        className="h-6 w-6"
        onClick={() => handleThumbsClick(1)}
        disabled={isSubmitting}
        title={feedback === 1 ? "Remove feedback" : "Good response"}
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
            disabled={isSubmitting}
            title={feedback === -1 ? "Remove feedback" : "Bad response"}
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
