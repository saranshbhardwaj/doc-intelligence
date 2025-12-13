/**
 * DeleteConfirmDialog Component
 *
 * Simple delete confirmation dialog for workflow runs, extractions, chat sessions, etc.
 * ChatGPT-inspired design matching EnhancedDeleteWarning aesthetic.
 *
 * Input:
 *   - itemId: string (ID of item to delete)
 *   - itemName: string (display name)
 *   - itemType: string (e.g., "workflow run", "extraction", "chat session")
 *   - deleteApiCall: (getToken, itemId) => Promise (API call function)
 *   - getToken: () => Promise<string>
 *   - onSuccess: () => void (callback after successful deletion)
 *   - trigger: React.ReactNode (the button/element that triggers the dialog)
 *   - warningMessage: string (optional custom warning, default based on itemType)
 *
 * Output:
 *   - Renders simple AlertDialog with delete confirmation
 *   - Calls delete API and handles success/error
 */

import { useState } from "react";
import { AlertTriangle } from "lucide-react";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "../ui/alert-dialog";

export default function DeleteConfirmDialog({
  itemId,
  itemName,
  itemType = "item",
  deleteApiCall,
  getToken,
  onSuccess,
  trigger,
  warningMessage,
}) {
  const [isOpen, setIsOpen] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);

  const handleConfirm = async () => {
    if (!deleteApiCall) {
      console.error("DeleteConfirmDialog: deleteApiCall is required");
      return;
    }

    setIsDeleting(true);
    try {
      await deleteApiCall(getToken, itemId);

      // Close dialog
      setIsOpen(false);

      // Call success callback
      if (onSuccess) {
        onSuccess();
      }
    } catch (error) {
      console.error(`Failed to delete ${itemType}:`, error);
      alert(
        `Failed to delete ${itemType}: ` +
          (error.response?.data?.detail || error.message)
      );
    } finally {
      setIsDeleting(false);
    }
  };

  const handleCancel = () => {
    setIsOpen(false);
  };

  const defaultWarning = warningMessage ||
    `This will permanently delete this ${itemType} and all associated artifacts from storage. This action cannot be undone.`;

  return (
    <AlertDialog open={isOpen} onOpenChange={setIsOpen}>
      <AlertDialogTrigger asChild>{trigger}</AlertDialogTrigger>

      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-destructive" />
            Delete {itemType.charAt(0).toUpperCase() + itemType.slice(1)}?
          </AlertDialogTitle>

          <AlertDialogDescription className="space-y-3">
            <p>
              Are you sure you want to delete{" "}
              <strong className="text-foreground">{itemName}</strong>?
            </p>

            <p className="text-sm text-muted-foreground">
              {defaultWarning}
            </p>
          </AlertDialogDescription>
        </AlertDialogHeader>

        <AlertDialogFooter>
          <AlertDialogCancel onClick={handleCancel} disabled={isDeleting}>
            Cancel
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirm}
            disabled={isDeleting}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {isDeleting ? "Deleting..." : "Delete"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
