/**
 * Chat Page
 *
 * Main chat interface for a specific collection.
 * Features:
 * - Chat with documents using RAG
 * - View past sessions (sidebar)
 * - Upload new documents to collection
 * - Export chat sessions
 */

import { useEffect, useState, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useAuth } from "@clerk/clerk-react";
import {
  Send,
  Plus,
  Upload,
  FileText,
  Download,
  Trash2,
  MessageSquare,
  X,
  UploadCloud,
  ChevronDown,
  ChevronUp,
  CheckCircle,
  XCircle,
  Clock,
  Library,
} from "lucide-react";
import { useChat, useChatActions } from "../store";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Progress } from "../components/ui/progress";
import { Label } from "../components/ui/label";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "../components/ui/select";
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
} from "../components/ui/alert-dialog";
import Spinner from "../components/common/Spinner";
import AppLayout from "../components/layout/AppLayout";
import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export default function ChatPage() {
  const { collectionId } = useParams();
  const navigate = useNavigate();
  const { getToken, isLoaded } = useAuth();
  const chat = useChat();
  const actions = useChatActions();

  const [message, setMessage] = useState("");
  const [showUploader, setShowUploader] = useState(false);
  const [uploadFile, setUploadFile] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [showDocuments, setShowDocuments] = useState(false);
  const [collections, setCollections] = useState([]);
  const [uploadToCollection, setUploadToCollection] = useState(collectionId); // Default to current collection
  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);

  useEffect(() => {
    // Wait for Clerk to initialize before making API calls
    if (!isLoaded) return;
    if (collectionId) {
      actions.selectCollection(getToken, collectionId);
    } else {
      fetchCollections();
    }
  }, [collectionId, isLoaded]);

  useEffect(() => {
    // Scroll to bottom when new messages arrive
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat.messages, chat.streamingMessage]);

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!message.trim() || chat.isStreaming) return;

    const userMessage = message.trim();
    setMessage("");

    await actions.sendMessage(getToken, collectionId, userMessage);
  };

  const handleSelectSession = async (sessionId) => {
    await actions.loadChatHistory(getToken, sessionId);
  };

  const fetchCollections = async () => {
    try {
      const token = await getToken();
      const res = await axios.get(`${API_BASE}/api/chat/collections`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      setCollections(res.data);
    } catch (error) {
      console.error("Failed to fetch collections:", error);
    }
  };

  const handleNewChat = () => {
    console.log("New Chat clicked");
    actions.startNewChat();
    setMessage(""); // Clear input field
  };

  const handleUploadDocument = async (e) => {
    e.preventDefault();
    if (!uploadFile) return;

    try {
      await actions.uploadDocumentToCollection(
        getToken,
        uploadToCollection, // Use selected collection instead of current
        uploadFile
      );
      // Only close on success
      setUploadFile(null);
      // Don't close uploader immediately - let user see the progress
    } catch (error) {
      // Error is handled in the store, just keep dialog open
      console.error("Upload failed:", error);
    }
  };

  const handleFileSelect = (file) => {
    if (file && file.type === "application/pdf") {
      setUploadFile(file);
    } else {
      alert("Please select a PDF file");
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    handleFileSelect(file);
  };

  const handleExportSession = async () => {
    if (!chat.currentSession) return;

    try {
      const exportData = await actions.exportSession(
        getToken,
        chat.currentSession.id
      );

      // Convert to markdown format
      let markdown = `# ${exportData.session.title}\n\n`;
      markdown += `**Collection:** ${exportData.collection.name}\n`;
      markdown += `**Date:** ${new Date(
        exportData.session.created_at
      ).toLocaleString()}\n\n`;
      markdown += `---\n\n`;

      exportData.messages.forEach((msg) => {
        const role = msg.role === "user" ? "You" : "Assistant";
        markdown += `### ${role}\n\n${msg.content}\n\n`;

        if (msg.source_chunks && msg.source_chunks.length > 0) {
          markdown += `*Sources: ${msg.num_chunks_retrieved} chunks*\n\n`;
        }
      });

      // Download as markdown file
      const blob = new Blob([markdown], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `chat-${exportData.session.title
        .replace(/[^a-z0-9]/gi, "-")
        .toLowerCase()}.md`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      alert("Failed to export session: " + error.message);
    }
  };

  if (chat.collectionLoading) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center min-h-screen">
          <Spinner />
        </div>
      </AppLayout>
    );
  }

  if (chat.collectionError) {
    return (
      <AppLayout>
        <div className="flex flex-col items-center justify-center min-h-screen">
          <p className="text-red-600 mb-4">{chat.collectionError}</p>
          <Button onClick={() => navigate("/app/library")}>
            Back to Library
          </Button>
        </div>
      </AppLayout>
    );
  }

  const breadcrumbs = chat.currentCollection
    ? [
        { label: "Library", href: "/app/library" },
        { label: chat.currentCollection.name },
      ]
    : [];

  return (
    <AppLayout breadcrumbs={breadcrumbs}>
      <div className="flex h-[calc(100vh-120px)] bg-background ">
        {/* Sidebar - Sessions */}
        <div className="w-64 bg-card border-r border-border dark:border-gray-700 flex flex-col">
          <div className="p-4 border-b border-border dark:border-gray-700">
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate("/app/library")}
              className="w-full mb-3"
            >
              <Library className="w-4 h-4 mr-2" />
              Library
            </Button>
            <Button onClick={handleNewChat} className="w-full">
              <Plus className="w-4 h-4 mr-2" />
              New Chat
            </Button>
          </div>

          <div className="flex-1 overflow-y-auto">
            {chat.sessionsLoading ? (
              <div className="p-4 text-center">
                <Spinner size="sm" />
              </div>
            ) : chat.sessions.length === 0 ? (
              <div className="p-4 text-center text-sm text-muted-foreground">
                No chat sessions yet
              </div>
            ) : (
              <div className="p-2">
                {chat.sessions.map((session) => (
                  <button
                    key={session.id}
                    onClick={() => handleSelectSession(session.id)}
                    className={`w-full text-left p-3 rounded-lg mb-2 transition-colors ${
                      chat.currentSession?.id === session.id
                        ? "bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800"
                        : "hover:bg-background dark:hover:bg-gray-700"
                    }`}
                  >
                    <div className="font-medium text-sm text-foreground truncate">
                      {session.title}
                    </div>
                    <div className="text-xs text-muted-foreground dark:text-muted-foreground mt-1">
                      {session.message_count} messages
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Collection Info */}
          {chat.currentCollection && (
            <div className="border-t border-border dark:border-gray-700">
              <div className="p-4">
                <div className="text-xs font-medium text-muted-foreground dark:text-muted-foreground mb-2">
                  Collection
                </div>
                <div className="text-sm font-medium text-foreground mb-1">
                  {chat.currentCollection.name}
                </div>

                <button
                  onClick={() => setShowDocuments(!showDocuments)}
                  className="flex items-center justify-between w-full text-xs text-muted-foreground dark:text-gray-300 hover:text-foreground dark:hover:text-foreground transition-colors py-2"
                >
                  <div className="flex items-center gap-2">
                    <FileText className="w-3 h-3" />
                    {chat.currentCollection.document_count} documents
                  </div>
                  {showDocuments ? (
                    <ChevronUp className="w-4 h-4" />
                  ) : (
                    <ChevronDown className="w-4 h-4" />
                  )}
                </button>

                {showDocuments && chat.currentCollection.documents && (
                  <div className="mt-2 space-y-2 max-h-48 overflow-y-auto">
                    {chat.currentCollection.documents.map((doc) => (
                      <div
                        key={doc.id}
                        className="p-2 bg-background dark:bg-card rounded text-xs"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <p className="font-medium text-foreground truncate">
                              {doc.filename}
                            </p>
                            <p className="text-muted-foreground dark:text-muted-foreground mt-0.5">
                              {doc.chunk_count} chunks · {doc.page_count} pages
                            </p>
                          </div>
                          <div className="flex items-center gap-2">
                            <div>
                              {doc.status === "completed" && (
                                <CheckCircle className="w-4 h-4 text-green-500" />
                              )}
                              {doc.status === "processing" && (
                                <Clock className="w-4 h-4 text-blue-500" />
                              )}
                              {doc.status === "failed" && (
                                <XCircle className="w-4 h-4 text-red-500" />
                              )}
                            </div>
                            <AlertDialog>
                              <AlertDialogTrigger asChild>
                                <button
                                  className="text-muted-foreground hover:text-red-500 transition-colors"
                                  title="Delete document"
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                              </AlertDialogTrigger>
                              <AlertDialogContent>
                                <AlertDialogHeader>
                                  <AlertDialogTitle>
                                    Delete Document?
                                  </AlertDialogTitle>
                                  <AlertDialogDescription>
                                    This will permanently delete{" "}
                                    <strong>{doc.filename}</strong> and all its
                                    chunks from this collection. This action
                                    cannot be undone.
                                  </AlertDialogDescription>
                                </AlertDialogHeader>
                                <AlertDialogFooter>
                                  <AlertDialogCancel>Cancel</AlertDialogCancel>
                                  <AlertDialogAction
                                    onClick={() =>
                                      actions.deleteDocument(getToken, doc.id)
                                    }
                                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                                  >
                                    Delete
                                  </AlertDialogAction>
                                </AlertDialogFooter>
                              </AlertDialogContent>
                            </AlertDialog>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowUploader(!showUploader)}
                  className="w-full mt-3"
                >
                  <Upload className="w-4 h-4 mr-2" />
                  Upload Document
                </Button>
              </div>
            </div>
          )}
        </div>

        {/* Main Chat Area */}
        <div className="flex-1 flex flex-col">
          {/* Export Button */}
          {chat.currentSession && (
            <div className="bg-card border-b border-border dark:border-gray-700 px-4 py-2">
              <div className="flex justify-end">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleExportSession}
                >
                  <Download className="w-4 h-4 mr-2" />
                  Export Chat
                </Button>
              </div>
            </div>
          )}

          {/* Document Uploader */}
          {showUploader && (
            <div className="border-b border-border dark:border-gray-700 bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-gray-800 dark:to-gray-900 p-6">
              <div className="max-w-2xl mx-auto">
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-semibold text-foreground">
                    Upload Document
                  </h3>
                  <button
                    onClick={() => {
                      setShowUploader(false);
                      setUploadFile(null);
                    }}
                    className="text-muted-foreground hover:text-muted-foreground dark:hover:text-gray-300 transition-colors"
                  >
                    <X className="w-5 h-5" />
                  </button>
                </div>

                {/* Upload Status: Uploading/Indexing */}
                {chat.uploadStatus === "uploading" ||
                chat.uploadStatus === "indexing" ? (
                  <div className="space-y-4">
                    <Card className="p-6 bg-card">
                      <div className="flex items-center gap-4 mb-4">
                        <div className="w-12 h-12 rounded-lg bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                          <FileText className="w-6 h-6 text-blue-600 dark:text-blue-400" />
                        </div>
                        <div className="flex-1">
                          <p className="font-medium text-foreground">
                            {uploadFile?.name}
                          </p>
                          <p className="text-sm text-muted-foreground dark:text-muted-foreground">
                            {chat.uploadStatus === "uploading"
                              ? "Uploading..."
                              : "Indexing..."}
                          </p>
                        </div>
                        <Spinner />
                      </div>
                      <Progress value={chat.uploadProgress} className="h-2" />
                      {chat.uploadProgress > 0 && (
                        <p className="text-xs text-muted-foreground dark:text-muted-foreground mt-2 text-right">
                          {chat.uploadProgress}% complete
                        </p>
                      )}
                    </Card>
                  </div>
                ) : uploadFile ? (
                  /* File Selected - Show Preview */
                  <form onSubmit={handleUploadDocument} className="space-y-4">
                    <Card className="p-4 bg-card">
                      <div className="flex items-center gap-4">
                        <div className="w-12 h-12 rounded-lg bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                          <FileText className="w-6 h-6 text-blue-600 dark:text-blue-400" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="font-medium text-foreground truncate">
                            {uploadFile.name}
                          </p>
                          <p className="text-sm text-muted-foreground dark:text-muted-foreground">
                            {(uploadFile.size / 1024 / 1024).toFixed(2)} MB
                          </p>
                        </div>
                        <button
                          type="button"
                          onClick={() => setUploadFile(null)}
                          className="text-muted-foreground hover:text-red-500 transition-colors"
                        >
                          <X className="w-5 h-5" />
                        </button>
                      </div>
                    </Card>

                    {/* Collection Selector */}
                    <div>
                      <Label className="text-sm text-muted-foreground dark:text-gray-300 mb-2 block">
                        Upload to Collection
                      </Label>
                      <Select
                        value={uploadToCollection || ""}
                        onValueChange={setUploadToCollection}
                      >
                        <SelectTrigger className="bg-card">
                          <SelectValue placeholder="Select collection" />
                        </SelectTrigger>
                        <SelectContent>
                          {collections.map((col) => (
                            <SelectItem key={col.id} value={col.id}>
                              {col.name}
                              {col.id === collectionId && " (Current)"}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <p className="text-xs text-muted-foreground dark:text-muted-foreground mt-1">
                        Document will be parsed, chunked, and embedded
                        automatically
                      </p>
                    </div>

                    <div className="flex gap-3">
                      <Button type="submit" className="flex-1">
                        <Upload className="w-4 h-4 mr-2" />
                        Upload & Index
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => {
                          setShowUploader(false);
                          setUploadFile(null);
                        }}
                      >
                        Cancel
                      </Button>
                    </div>
                  </form>
                ) : (
                  /* Drag & Drop Zone */
                  <div
                    onDragOver={handleDragOver}
                    onDragLeave={handleDragLeave}
                    onDrop={handleDrop}
                    onClick={() => fileInputRef.current?.click()}
                    className={`relative border-2 border-dashed rounded-lg p-8 transition-all cursor-pointer ${
                      isDragging
                        ? "border-blue-500 bg-blue-50 dark:bg-blue-900/20 scale-105"
                        : "border-border dark:border-gray-600 hover:border-blue-400 dark:hover:border-blue-500 bg-card"
                    }`}
                  >
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".pdf"
                      onChange={(e) => handleFileSelect(e.target.files[0])}
                      className="hidden"
                    />
                    <div className="flex flex-col items-center gap-4 text-center">
                      <div className="w-16 h-16 rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center">
                        <UploadCloud className="w-8 h-8 text-blue-600 dark:text-blue-400" />
                      </div>
                      <div>
                        <p className="text-lg font-medium text-foreground mb-1">
                          {isDragging
                            ? "Drop your PDF here"
                            : "Drop PDF here or click to browse"}
                        </p>
                        <p className="text-sm text-muted-foreground dark:text-muted-foreground">
                          Supports PDF files up to 50MB
                        </p>
                      </div>
                    </div>
                  </div>
                )}

                {chat.uploadError && (
                  <div className="mt-4 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                    <p className="text-sm text-red-600 dark:text-red-400">
                      {chat.uploadError}
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-6 space-y-4">
            {chat.messages.length === 0 && !chat.currentSession ? (
              <div className="flex flex-col items-center justify-center h-full text-center">
                <MessageSquare className="w-16 h-16 text-gray-300 dark:text-muted-foreground mb-4" />
                <h3 className="text-xl font-medium text-foreground mb-2">
                  Start a conversation
                </h3>
                <p className="text-muted-foreground dark:text-gray-300 max-w-md">
                  Ask questions about your documents. The AI will search across
                  all documents in this collection to find relevant answers.
                </p>
              </div>
            ) : (
              <>
                {chat.messages.map((msg, index) => (
                  <div
                    key={index}
                    className={`flex ${
                      msg.role === "user" ? "justify-end" : "justify-start"
                    }`}
                  >
                    <Card
                      className={`max-w-3xl p-4 ${
                        msg.role === "user"
                          ? "bg-blue-600 text-foreground"
                          : "bg-card"
                      }`}
                    >
                      <div className="whitespace-pre-wrap">{msg.content}</div>
                      {msg.source_chunks && msg.source_chunks.length > 0 && (
                        <div className="mt-3 pt-3 border-t border-border dark:border-gray-700 text-xs text-muted-foreground">
                          Sources: {msg.num_chunks_retrieved} chunks used
                        </div>
                      )}
                    </Card>
                  </div>
                ))}

                {chat.isStreaming && chat.streamingMessage && (
                  <div className="flex justify-start">
                    <Card className="max-w-3xl p-4 bg-card">
                      <div className="whitespace-pre-wrap">
                        {chat.streamingMessage}
                      </div>
                      <div className="mt-2">
                        <Spinner size="sm" />
                      </div>
                    </Card>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </>
            )}
          </div>

          {/* Input */}
          <div className="bg-card border-t border-border dark:border-gray-700 p-4">
            {chat.chatError && (
              <div className="mb-3 p-3 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 rounded-lg text-sm">
                {chat.chatError}
              </div>
            )}

            <form onSubmit={handleSendMessage} className="flex gap-3">
              <input
                type="text"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Ask a question about your documents..."
                disabled={chat.isStreaming || !chat.currentCollection}
                className="flex-1 px-4 py-3 border border-border dark:border-gray-600 rounded-lg bg-background dark:bg-gray-700 text-foreground disabled:bg-popover dark:disabled:bg-card disabled:cursor-not-allowed"
              />
              <Button
                type="submit"
                disabled={
                  !message.trim() || chat.isStreaming || !chat.currentCollection
                }
              >
                {chat.isStreaming ? (
                  <Spinner size="sm" />
                ) : (
                  <>
                    <Send className="w-4 h-4 mr-2" />
                    Send
                  </>
                )}
              </Button>
            </form>
          </div>
        </div>
      </div>
    </AppLayout>
  );
}
