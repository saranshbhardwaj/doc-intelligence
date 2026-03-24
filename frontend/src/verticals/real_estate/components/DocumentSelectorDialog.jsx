/**
 * Document Selector Dialog
 * Folder-first browsing with glass UI — select a PDF to fill a template
 */

import React, { useState, useEffect, useMemo } from 'react';
import { useAppAuth } from "@/hooks/useAppAuth";
import {
  Dialog,
  DialogContent,
  DialogFooter,
} from '../../../components/ui/dialog';
import { Button } from '../../../components/ui/button';
import { Input } from '../../../components/ui/input';
import { ScrollArea } from '../../../components/ui/scroll-area';
import { FileText, Search, AlertCircle, CheckCircle2, Folder, FolderOpen, Sparkles, Files } from 'lucide-react';
import { cn } from '@/lib/utils';
import { listCollections } from '../../../api';

export default function DocumentSelectorDialog({ open, onOpenChange, onSelect, templateName }) {
  const { getToken } = useAppAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [collections, setCollections] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedDocKey, setSelectedDocKey] = useState(null);
  const [selectedCollectionId, setSelectedCollectionId] = useState(null); // null = All

  useEffect(() => {
    if (open) {
      loadDocuments();
      setSelectedCollectionId(null);
      setSearchQuery('');
      setSelectedDocKey(null);
    }
  }, [open]);

  async function loadDocuments() {
    try {
      setLoading(true);
      setError(null);

      const res = await listCollections(getToken, { includeDocuments: true });
      const cols = res?.collections || [];
      setCollections(cols.map(({ documents: _, ...c }) => c));

      const allDocs = cols.flatMap((col) =>
        (col.documents || []).map((doc) => ({
          ...doc,
          collectionName: col.name,
          collectionId: col.id,
          uiSelectionKey: `${col.id}:${doc.id}`,
        }))
      );
      setDocuments(allDocs);
    } catch (err) {
      console.error('Failed to load documents:', err);
      setError('Failed to load documents');
    } finally {
      setLoading(false);
    }
  }

  function handleSelect() {
    const selectedDoc = documents.find((d) => d.uiSelectionKey === selectedDocKey);
    if (selectedDoc) {
      onSelect(selectedDoc);
      onOpenChange(false);
    }
  }

  function handleCollectionChange(colId) {
    setSelectedCollectionId(colId);
    setSearchQuery('');
  }

  const readyDocuments = useMemo(
    () => documents.filter((doc) => doc.status === 'completed' && doc.has_embeddings),
    [documents]
  );

  const collectionFiltered = useMemo(
    () => selectedCollectionId
      ? readyDocuments.filter((d) => d.collectionId === selectedCollectionId)
      : readyDocuments,
    [readyDocuments, selectedCollectionId]
  );

  const filteredDocuments = useMemo(
    () => searchQuery
      ? collectionFiltered.filter((doc) =>
          doc.filename?.toLowerCase().includes(searchQuery.toLowerCase())
        )
      : collectionFiltered,
    [collectionFiltered, searchQuery]
  );

  const countByCollection = useMemo(() => {
    const counts = {};
    for (const doc of readyDocuments) {
      counts[doc.collectionId] = (counts[doc.collectionId] || 0) + 1;
    }
    return counts;
  }, [readyDocuments]);

  const selectedCollection = collections.find((c) => c.id === selectedCollectionId);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl max-h-[85vh] flex flex-col p-0 gap-0 overflow-hidden">
        {/* Header */}
        <div className="flex-shrink-0 px-6 pt-5 pb-4 border-b border-border/50">
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-xl bg-primary/10 flex items-center justify-center flex-shrink-0">
              <Sparkles className="h-4 w-4 text-primary" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-0.5">
                <h2 className="font-display text-base font-semibold text-foreground">Select Source Document</h2>
                <span className="inline-flex items-center gap-1 text-[10px] font-semibold bg-primary/10 text-primary px-2 py-0.5 rounded-full">
                  AI-Powered
                </span>
              </div>
              <p className="text-xs text-muted-foreground truncate">
                Choose the PDF to analyze and fill <span className="font-medium text-foreground">{templateName}</span>
              </p>
            </div>
          </div>
        </div>

        {/* Body: two-column */}
        <div className="flex flex-1 min-h-0 overflow-hidden">
          {/* Collection sidebar */}
          <div className="glass-panel w-44 flex-shrink-0 border-r border-border/40 flex flex-col overflow-hidden">
            <p className="px-3 pt-3 pb-1.5 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
              Collections
            </p>
            <ScrollArea className="flex-1">
              <div className="px-2 pb-3 space-y-0.5">
                {/* All Documents */}
                <button
                  onClick={() => handleCollectionChange(null)}
                  className={cn(
                    'w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-sm transition-all text-left',
                    !selectedCollectionId
                      ? 'bg-primary/10 text-primary font-medium'
                      : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'
                  )}
                >
                  <Files className="h-3.5 w-3.5 shrink-0" />
                  <span className="flex-1 truncate">All</span>
                  <span className="text-[10px] tabular-nums">{readyDocuments.length}</span>
                </button>

                {!loading && collections.map((col) => {
                  const count = countByCollection[col.id] || 0;
                  const active = selectedCollectionId === col.id;
                  return (
                    <button
                      key={col.id}
                      onClick={() => handleCollectionChange(col.id)}
                      className={cn(
                        'w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-sm transition-all text-left',
                        active
                          ? 'bg-primary/10 text-primary font-medium'
                          : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'
                      )}
                    >
                      {active
                        ? <FolderOpen className="h-3.5 w-3.5 shrink-0" />
                        : <Folder className="h-3.5 w-3.5 shrink-0" />
                      }
                      <span className="flex-1 truncate">{col.name}</span>
                      <span className="text-[10px] tabular-nums">{count}</span>
                    </button>
                  );
                })}
              </div>
            </ScrollArea>
          </div>

          {/* Right panel */}
          <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
            {/* Search */}
            <div className="flex-shrink-0 px-4 pt-3 pb-2">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                <Input
                  type="text"
                  placeholder={`Search in ${selectedCollection?.name || 'all documents'}…`}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-8 h-8 text-sm"
                />
              </div>
            </div>

            {/* Document list */}
            <ScrollArea className="flex-1 px-4 pb-3">
              {loading ? (
                <div className="flex flex-col items-center justify-center py-16 gap-3">
                  {[1, 2, 3].map((i) => (
                    <div key={i} className="w-full h-16 rounded-xl bg-muted/40 animate-pulse" />
                  ))}
                </div>
              ) : error ? (
                <div className="flex flex-col items-center justify-center py-12">
                  <AlertCircle className="h-10 w-10 text-destructive mb-3" />
                  <p className="text-sm text-destructive mb-3">{error}</p>
                  <Button onClick={loadDocuments} variant="outline" size="sm">Try Again</Button>
                </div>
              ) : filteredDocuments.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12">
                  <div className="glass-card w-14 h-14 rounded-2xl flex items-center justify-center mb-3">
                    <Folder className="h-6 w-6 text-muted-foreground" />
                  </div>
                  <p className="text-sm font-medium text-foreground mb-1">
                    {searchQuery ? `No matches for "${searchQuery}"` : 'No PDFs in this collection'}
                  </p>
                  {!searchQuery && (
                    <p className="text-xs text-muted-foreground">Upload a PDF to your library first</p>
                  )}
                </div>
              ) : (
                <div className="space-y-2 pt-1">
                  {filteredDocuments.map((doc) => (
                    <DocumentCard
                      key={doc.uiSelectionKey}
                      document={doc}
                      selected={doc.uiSelectionKey === selectedDocKey}
                      showCollection={!selectedCollectionId}
                      onSelect={() => setSelectedDocKey(doc.uiSelectionKey)}
                    />
                  ))}
                </div>
              )}
            </ScrollArea>
          </div>
        </div>

        {/* Footer */}
        <DialogFooter className="flex-shrink-0 border-t border-border/50 px-6 py-3">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button size="sm" onClick={handleSelect} disabled={!selectedDocKey} className="gap-2">
            <Sparkles className="h-3.5 w-3.5" />
            Start AI Fill
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function DocumentCard({ document, selected, showCollection, onSelect }) {
  return (
    <button
      onClick={onSelect}
      className={cn(
        'w-full text-left p-3 rounded-xl border transition-all',
        selected
          ? 'glass-card border-primary/30 shadow-sm'
          : 'border-border/60 hover:border-primary/20 hover:bg-primary/5'
      )}
    >
      <div className="flex items-center gap-3">
        <div
          className={cn(
            'w-9 h-9 rounded-xl flex items-center justify-center flex-shrink-0',
            selected ? 'bg-primary/15' : 'bg-muted/70'
          )}
        >
          <FileText className={cn('h-4 w-4', selected ? 'text-primary' : 'text-muted-foreground')} />
        </div>

        <div className="flex-1 min-w-0">
          <p className={cn('text-sm font-medium truncate', selected ? 'text-primary' : 'text-foreground')}>
            {document.filename}
          </p>
          <div className="flex items-center gap-2 mt-0.5 text-xs text-muted-foreground">
            {showCollection && (
              <span className="truncate max-w-[120px]">{document.collectionName}</span>
            )}
            {showCollection && document.page_count && <span className="shrink-0">·</span>}
            {document.page_count && <span className="shrink-0">{document.page_count}p</span>}
          </div>
        </div>

        {selected && (
          <CheckCircle2 className="h-4 w-4 text-primary flex-shrink-0" />
        )}
      </div>
    </button>
  );
}
