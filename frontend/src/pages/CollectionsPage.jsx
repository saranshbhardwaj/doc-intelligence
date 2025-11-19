/**
 * Collections Page
 *
 * Main page for Chat Mode - displays user's document collections
 * and allows creating new collections or selecting one to chat with.
 */

import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth, UserButton, SignedIn } from "@clerk/clerk-react";
import { Plus, MessageSquare, FileText, Trash2 } from "lucide-react";
import { useChat, useChatActions } from "../store";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import Modal from "../components/common/Modal";
import Spinner from "../components/common/Spinner";
import DarkModeToggle from "../components/common/DarkModeToggle";
import { useDarkMode } from "../hooks/useDarkMode";

export default function CollectionsPage() {
  const navigate = useNavigate();
  const { getToken } = useAuth();
  const chat = useChat();
  const actions = useChatActions();
  const { isDark, toggle } = useDarkMode();

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newCollectionName, setNewCollectionName] = useState("");
  const [newCollectionDescription, setNewCollectionDescription] = useState("");
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    actions.fetchCollections(getToken);
  }, []);

  const handleCreateCollection = async (e) => {
    e.preventDefault();
    if (!newCollectionName.trim()) return;

    setCreating(true);
    try {
      await actions.createCollection(getToken, {
        name: newCollectionName.trim(),
        description: newCollectionDescription.trim() || null,
      });

      setShowCreateModal(false);
      setNewCollectionName("");
      setNewCollectionDescription("");
    } catch (error) {
      console.error("Failed to create collection:", error);
      alert("Failed to create collection: " + error.message);
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteCollection = async (collectionId, name) => {
    if (
      !confirm(
        `Delete collection "${name}"? This will delete all documents and chat sessions.`
      )
    ) {
      return;
    }

    try {
      await actions.deleteCollection(getToken, collectionId);
    } catch (error) {
      alert("Failed to delete collection: " + error.message);
    }
  };

  return (
    <div className="min-h-screen bg-background ">
      {/* Header */}
      <div className="bg-card border-b border-border dark:border-gray-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold text-foreground">
                Chat Collections
              </h1>
              <p className="mt-2 text-muted-foreground dark:text-gray-300">
                Create collections of documents and chat with them using AI
              </p>
            </div>
            <div className="flex items-center gap-3">
              <Button
                variant="outline"
                onClick={() => navigate("/app/dashboard")}
              >
                Back to Dashboard
              </Button>
              <Button onClick={() => setShowCreateModal(true)}>
                <Plus className="w-4 h-4 mr-2" />
                New Collection
              </Button>
              <DarkModeToggle
                isDark={isDark}
                toggle={toggle}
                variant="inline"
              />
              <SignedIn>
                <UserButton
                  appearance={{
                    elements: {
                      avatarBox: "w-10 h-10",
                    },
                  }}
                />
              </SignedIn>
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {chat.collectionsLoading ? (
          <div className="flex justify-center items-center py-16">
            <Spinner />
          </div>
        ) : chat.collectionsError ? (
          <div className="text-center py-16">
            <p className="text-red-600 dark:text-red-400">
              {chat.collectionsError}
            </p>
            <Button
              onClick={() => actions.fetchCollections(getToken)}
              className="mt-4"
            >
              Retry
            </Button>
          </div>
        ) : chat.collections.length === 0 ? (
          <div className="text-center py-16">
            <MessageSquare className="w-16 h-16 mx-auto text-muted-foreground mb-4" />
            <h3 className="text-xl font-medium text-foreground mb-2">
              No collections yet
            </h3>
            <p className="text-muted-foreground dark:text-gray-300 mb-6">
              Create your first collection to start chatting with documents
            </p>
            <Button onClick={() => setShowCreateModal(true)}>
              <Plus className="w-4 h-4 mr-2" />
              Create Collection
            </Button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {chat.collections.map((collection) => (
              <Card
                key={collection.id}
                className="p-6 hover:shadow-lg transition-shadow cursor-pointer"
                onClick={() => navigate(`/app/chat/${collection.id}`)}
              >
                <div className="flex items-start justify-between mb-4">
                  <div className="flex-1">
                    <h3 className="font-semibold text-lg text-foreground mb-1">
                      {collection.name}
                    </h3>
                    {collection.description && (
                      <p className="text-sm text-muted-foreground dark:text-gray-300">
                        {collection.description}
                      </p>
                    )}
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteCollection(collection.id, collection.name);
                    }}
                    className="text-muted-foreground hover:text-red-600 transition-colors"
                  >
                    <Trash2 className="w-5 h-5" />
                  </button>
                </div>

                <div className="flex items-center gap-6 text-sm text-muted-foreground dark:text-gray-300">
                  <div className="flex items-center gap-2">
                    <FileText className="w-4 h-4" />
                    <span>
                      {collection.document_count || 0}{" "}
                      {collection.document_count === 1
                        ? "document"
                        : "documents"}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <MessageSquare className="w-4 h-4" />
                    <span>{collection.total_chunks || 0} chunks</span>
                  </div>
                </div>

                <div className="mt-4 pt-4 border-t border-border dark:border-gray-700">
                  <p className="text-xs text-muted-foreground dark:text-muted-foreground">
                    Created{" "}
                    {new Date(collection.created_at).toLocaleDateString()}
                  </p>
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Create Collection Modal */}
      <Modal isOpen={showCreateModal} onClose={() => setShowCreateModal(false)}>
        <div className="p-6">
          <h2 className="text-2xl font-bold text-foreground mb-4">
            Create New Collection
          </h2>
          <form onSubmit={handleCreateCollection} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-muted-foreground dark:text-gray-300 mb-2">
                Collection Name *
              </label>
              <input
                type="text"
                value={newCollectionName}
                onChange={(e) => setNewCollectionName(e.target.value)}
                placeholder="e.g., Q3 Financial Reports"
                className="w-full px-4 py-2 border border-border dark:border-gray-600 rounded-lg bg-card text-foreground"
                required
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-muted-foreground dark:text-gray-300 mb-2">
                Description (optional)
              </label>
              <textarea
                value={newCollectionDescription}
                onChange={(e) => setNewCollectionDescription(e.target.value)}
                placeholder="What is this collection for?"
                rows={3}
                className="w-full px-4 py-2 border border-border dark:border-gray-600 rounded-lg bg-card text-foreground"
              />
            </div>

            <div className="flex justify-end gap-3 mt-6">
              <Button
                type="button"
                variant="outline"
                onClick={() => setShowCreateModal(false)}
                disabled={creating}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={creating || !newCollectionName.trim()}
              >
                {creating ? <Spinner size="sm" /> : "Create"}
              </Button>
            </div>
          </form>
        </div>
      </Modal>
    </div>
  );
}
