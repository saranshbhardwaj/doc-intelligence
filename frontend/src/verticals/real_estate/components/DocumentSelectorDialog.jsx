/**
 * Document Selector Dialog
 * Select a PDF document to fill with template data
 */

import React, { useState, useEffect } from 'react';
import { useAuth } from '@clerk/clerk-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../../../components/ui/dialog';
import { Button } from '../../../components/ui/button';
import { Badge } from '../../../components/ui/badge';
import { Input } from '../../../components/ui/input';
import { ScrollArea } from '../../../components/ui/scroll-area';
import { FileText, Search, Loader2, AlertCircle, CheckCircle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { listCollections, getCollection } from '../../../api';

export default function DocumentSelectorDialog({ open, onOpenChange, onSelect, templateName }) {
  const { getToken } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [collections, setCollections] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedDocId, setSelectedDocId] = useState(null);

  useEffect(() => {
    if (open) {
      loadDocuments();
    }
  }, [open]);

  async function loadDocuments() {
    try {
      setLoading(true);
      setError(null);

      // Fetch all collections
      const res = await listCollections(getToken);
      const cols = res?.collections || [];
      setCollections(cols);

      // Fetch documents from all collections
      const allDocs = [];
      for (const col of cols) {
        try {
          const collectionData = await getCollection(getToken, col.id);
          const colDocs = (collectionData?.documents || []).map((doc) => ({
            ...doc,
            collectionName: col.name,
            collectionId: col.id,
          }));
          allDocs.push(...colDocs);
        } catch (err) {
          console.warn(`Failed to load collection ${col.name}:`, err);
        }
      }

      setDocuments(allDocs);
    } catch (err) {
      console.error('Failed to load documents:', err);
      setError('Failed to load documents');
    } finally {
      setLoading(false);
    }
  }

  function handleSelect() {
    const selectedDoc = documents.find((d) => d.id === selectedDocId);
    if (selectedDoc) {
      onSelect(selectedDoc);
      onOpenChange(false);
      setSelectedDocId(null);
      setSearchQuery('');
    }
  }

  const filteredDocuments = documents.filter(
    (doc) =>
      doc.filename?.toLowerCase().includes(searchQuery.toLowerCase()) ||
      doc.collectionName?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  // Only show completed documents with embeddings (ready for processing)
  const readyDocuments = filteredDocuments.filter(
    (doc) => doc.status === 'completed' && doc.has_embeddings
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl max-h-[85vh] flex flex-col">
        <DialogHeader className="flex-shrink-0">
          <DialogTitle>Select PDF Document</DialogTitle>
          <DialogDescription>
            Choose a PDF to fill the template: <span className="font-semibold">{templateName}</span>
          </DialogDescription>
        </DialogHeader>

        {/* Search */}
        <div className="flex-shrink-0 px-1">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              type="text"
              placeholder="Search documents..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
          </div>
        </div>

        {/* Document List */}
        <ScrollArea className="flex-1 overflow-y-auto px-1">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          ) : error ? (
            <div className="flex flex-col items-center justify-center py-12">
              <AlertCircle className="h-12 w-12 text-destructive mb-3" />
              <p className="text-sm text-destructive">{error}</p>
              <Button onClick={loadDocuments} variant="outline" size="sm" className="mt-4">
                Try Again
              </Button>
            </div>
          ) : readyDocuments.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <FileText className="h-12 w-12 mb-3 text-muted-foreground/50" />
              <p className="text-sm font-medium">No documents found</p>
              <p className="text-xs mt-1">Upload a PDF to the library first</p>
            </div>
          ) : (
            <div className="space-y-2">
              {readyDocuments.map((doc) => (
                <DocumentCard
                  key={doc.id}
                  document={doc}
                  selected={doc.id === selectedDocId}
                  onSelect={() => setSelectedDocId(doc.id)}
                />
              ))}
            </div>
          )}
        </ScrollArea>

        <DialogFooter className="flex-shrink-0 border-t pt-4">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSelect} disabled={!selectedDocId}>
            Select Document
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DocumentCard({ document, selected, onSelect }) {
  return (
    <button
      onClick={onSelect}
      className={cn(
        'w-full text-left p-3 rounded-lg border transition-all',
        selected
          ? 'border-primary bg-primary/5 ring-2 ring-primary/20'
          : 'border-border hover:border-primary/50 hover:bg-accent/50'
      )}
    >
      <div className="flex items-start gap-3">
        <div
          className={cn(
            'p-2 rounded-lg flex-shrink-0',
            selected ? 'bg-primary/10' : 'bg-muted'
          )}
        >
          <FileText
            className={cn('h-5 w-5', selected ? 'text-primary' : 'text-muted-foreground')}
          />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <h4 className="font-medium text-sm truncate">{document.filename}</h4>
            {selected && <CheckCircle className="h-4 w-4 text-primary flex-shrink-0" />}
          </div>

          <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground">
            <Badge variant="outline" className="text-xs">
              {document.collectionName}
            </Badge>
            {document.page_count && <span>{document.page_count} pages</span>}
            {document.file_size_bytes && (
              <span>{Math.round(document.file_size_bytes / 1024)} KB</span>
            )}
          </div>

          {document.parser_used && (
            <p className="text-xs text-muted-foreground mt-1">
              Parsed with {document.parser_used}
            </p>
          )}
        </div>
      </div>
    </button>
  );
}
