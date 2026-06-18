/**
 * CollectionsSidebar Component
 *
 * Compact sidebar for browsing collections with search
 *
 * Input:
 *   - collections: Array<{id, name, document_count}>
 *   - selectedCollection: {id, name}
 *   - loading: boolean
 *   - onSelectCollection: (collection) => void
 *   - onCreateCollection: (name) => void
 *   - onDeleteCollection: (collectionId) => void
 */

import { useState, useMemo, useEffect } from "react";
import { Folder, Plus, Search, Trash2 } from "lucide-react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
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
import Spinner from "../common/Spinner";

export default function CollectionsSidebar({
  collections = [],
  selectedCollection = null,
  loading = false,
  onSelectCollection,
  onCreateCollection,
  onDeleteCollection,
  requestCreate = 0,
}) {
  const [searchQuery, setSearchQuery] = useState("");
  const [showNewCollection, setShowNewCollection] = useState(false);
  const [newCollectionName, setNewCollectionName] = useState("");
  const [creatingCollection, setCreatingCollection] = useState(false);

  // Allow external callers (e.g. empty state buttons) to trigger create form
  useEffect(() => {
    if (requestCreate > 0) {
      setShowNewCollection(true);
    }
  }, [requestCreate]);

  // Filter collections by search query
  const filteredCollections = useMemo(() => {
    if (!searchQuery.trim()) return collections;
    const query = searchQuery.toLowerCase();
    return collections.filter((col) =>
      col.name.toLowerCase().includes(query)
    );
  }, [collections, searchQuery]);

  const handleCreateCollection = async () => {
    if (!newCollectionName.trim()) return;
    try {
      setCreatingCollection(true);
      await onCreateCollection?.(newCollectionName.trim());
      setNewCollectionName("");
      setShowNewCollection(false);
    } finally {
      setCreatingCollection(false);
    }
  };

  return (
    <div className="h-full flex min-h-0 flex-col px-4 py-4 sm:px-5">
      <div className="shrink-0">
        <div className="mb-4 flex items-start justify-between gap-3 border-b border-border/70 pb-4">
          <div>
            <h2 className="text-[0.72rem] font-semibold uppercase tracking-[0.22em] text-muted-foreground">
              Collections
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              {collections.length} total
            </p>
          </div>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setShowNewCollection(true)}
            className="h-9 w-9 rounded-full"
          >
            <Plus className="w-4 h-4" />
          </Button>
        </div>

        <div className="relative mb-3">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Find a collection"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="h-10 rounded-xl border-border/70 bg-background/70 pl-8 text-sm"
          />
        </div>

        {searchQuery && (
          <p className="mb-2 text-xs text-muted-foreground">
            {filteredCollections.length} match{filteredCollections.length === 1 ? "" : "es"}
          </p>
        )}
      </div>

      <div className="library-scrollbar flex-1 space-y-1 overflow-y-auto pr-1">
        {loading ? (
          <div className="flex justify-center py-8">
            <Spinner size="sm" />
          </div>
        ) : filteredCollections.length === 0 ? (
          <div className="text-center py-8">
            <Folder className="w-8 h-8 text-muted-foreground mx-auto mb-2 opacity-40" />
            <p className="text-xs text-muted-foreground">
              {searchQuery ? "No matches found" : "No collections yet"}
            </p>
          </div>
        ) : (
          filteredCollections.map((col) => {
            const isActive = selectedCollection?.id === col.id;
            return (
              <div
                key={col.id}
                className={`library-sidebar-item group cursor-pointer ${
                  isActive ? "library-sidebar-item-active" : ""
                }`}
                onClick={() => onSelectCollection?.(col)}
              >
                <Folder
                  className={`w-4 h-4 flex-shrink-0 ${
                    isActive ? "text-primary" : "text-muted-foreground"
                  }`}
                />
                <div className="flex-1 min-w-0">
                  <p
                    className={`truncate text-sm font-medium ${
                      isActive ? "text-foreground" : "text-foreground"
                    }`}
                  >
                    {col.name}
                  </p>
                  <p className="text-[0.7rem] uppercase tracking-[0.18em] text-muted-foreground">
                    Workspace
                  </p>
                </div>
                <span className="library-sidebar-count">
                  {col.document_count || 0}
                </span>

                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <button
                      onClick={(e) => e.stopPropagation()}
                      className="rounded-full p-1 opacity-0 transition-opacity group-hover:opacity-100 hover:bg-destructive/10"
                    >
                      <Trash2 className="w-3.5 h-3.5 text-muted-foreground hover:text-destructive" />
                    </button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>Delete Collection?</AlertDialogTitle>
                      <AlertDialogDescription>
                        This will delete "{col.name}" and all its documents. This
                        action cannot be undone.
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>Cancel</AlertDialogCancel>
                      <AlertDialogAction
                        onClick={() => onDeleteCollection?.(col.id)}
                        className="bg-destructive hover:bg-destructive/90"
                      >
                        Delete
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </div>
            );
          })
        )}
      </div>

      {showNewCollection && (
        <div className="mt-4 shrink-0 border-t border-border/70 pt-4">
          <Input
            placeholder="Collection name"
            value={newCollectionName}
            onChange={(e) => setNewCollectionName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreateCollection()}
            className="mb-2 h-10 rounded-xl border-border/70 bg-background/70 text-sm"
            autoFocus
            disabled={creatingCollection}
          />
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={handleCreateCollection}
              disabled={creatingCollection || !newCollectionName.trim()}
              className="h-9 flex-1 rounded-full"
            >
              {creatingCollection ? "Creating..." : "Create"}
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setShowNewCollection(false);
                setNewCollectionName("");
              }}
              disabled={creatingCollection}
              className="h-9 flex-1 rounded-full"
            >
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
