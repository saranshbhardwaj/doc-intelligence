/**
 * CollectionsSidebar Component
 *
 * Compact sidebar for browsing collections with search
 * ChatGPT-inspired design with filtering
 *
 * Input:
 *   - collections: Array<{id, name, document_count}>
 *   - selectedCollection: {id, name}
 *   - loading: boolean
 *   - onSelectCollection: (collection) => void
 *   - onCreateCollection: (name) => void
 *   - onDeleteCollection: (collectionId) => void
 */

import { useState, useMemo } from "react";
import { Folder, Plus, Search, Trash2 } from "lucide-react";
import { Button } from "../ui/button";
import { Card } from "../ui/card";
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
}) {
  const [searchQuery, setSearchQuery] = useState("");
  const [showNewCollection, setShowNewCollection] = useState(false);
  const [newCollectionName, setNewCollectionName] = useState("");

  // Filter collections by search query
  const filteredCollections = useMemo(() => {
    if (!searchQuery.trim()) return collections;
    const query = searchQuery.toLowerCase();
    return collections.filter((col) =>
      col.name.toLowerCase().includes(query)
    );
  }, [collections, searchQuery]);

  const handleCreateCollection = () => {
    if (!newCollectionName.trim()) return;
    onCreateCollection?.(newCollectionName.trim());
    setNewCollectionName("");
    setShowNewCollection(false);
  };

  return (
    <Card className="p-4 h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-foreground">Collections</h2>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setShowNewCollection(true)}
          className="h-7 w-7 p-0"
        >
          <Plus className="w-4 h-4" />
        </Button>
      </div>

      {/* Search */}
      <div className="relative mb-3">
        <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search collections..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="pl-8 h-9 text-sm"
        />
      </div>

      {/* Results count */}
      {searchQuery && (
        <p className="text-xs text-muted-foreground mb-2">
          {filteredCollections.length} of {collections.length} collections
        </p>
      )}

      {/* Collections List */}
      <div className="flex-1 overflow-y-auto space-y-1">
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
          filteredCollections.map((col) => (
            <div
              key={col.id}
              className={`group flex items-center gap-2 p-2 rounded-lg transition-all cursor-pointer ${
                selectedCollection?.id === col.id
                  ? "bg-primary/10 border border-primary/30"
                  : "hover:bg-muted/50"
              }`}
              onClick={() => onSelectCollection?.(col)}
            >
              <Folder
                className={`w-4 h-4 flex-shrink-0 ${
                  selectedCollection?.id === col.id
                    ? "text-primary"
                    : "text-muted-foreground"
                }`}
              />
              <div className="flex-1 min-w-0">
                <p
                  className={`text-sm font-medium truncate ${
                    selectedCollection?.id === col.id
                      ? "text-primary"
                      : "text-foreground"
                  }`}
                >
                  {col.name}
                </p>
                <p className="text-xs text-muted-foreground">
                  {col.document_count || 0} docs
                </p>
              </div>

              {/* Delete button - only show on hover */}
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <button
                    onClick={(e) => e.stopPropagation()}
                    className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:bg-destructive/10 rounded"
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
          ))
        )}
      </div>

      {/* New Collection Form */}
      {showNewCollection && (
        <div className="mt-3 pt-3 border-t border-border">
          <Input
            placeholder="Collection name"
            value={newCollectionName}
            onChange={(e) => setNewCollectionName(e.target.value)}
            onKeyPress={(e) => e.key === "Enter" && handleCreateCollection()}
            className="mb-2 h-9 text-sm"
            autoFocus
          />
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={handleCreateCollection}
              className="flex-1 h-8"
            >
              Create
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={() => {
                setShowNewCollection(false);
                setNewCollectionName("");
              }}
              className="flex-1 h-8"
            >
              Cancel
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}
