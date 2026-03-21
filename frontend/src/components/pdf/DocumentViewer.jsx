/**
 * DocumentViewer — routes to the correct renderer based on file type.
 *
 * - PDF (.pdf, or unknown extension) → PDFViewer (react-pdf)
 * - Office (.docx, .doc, .pptx, .ppt, .xlsx, .xls) → Microsoft Office Online iframe
 * - Image (.png, .jpg, .jpeg, .gif, .webp, .svg) → <img>
 * - Text / Markdown (.txt, .md) → fetched text in <pre>
 * - Unknown → download link
 *
 * Backward-compatible: accepts `pdfUrl` as an alias for `fileUrl`.
 */

import React, { useState, useEffect } from 'react';
import { FileText, FileDown, Loader2 } from 'lucide-react';
import PDFViewer from './PDFViewer';

const OFFICE_EXTENSIONS = ['doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx'];
const IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'gif', 'webp', 'svg', 'bmp', 'tif', 'tiff', 'heif', 'heic'];
const TEXT_EXTENSIONS = ['txt', 'md'];

function getExtension(value = '') {
  if (!value) return '';

  const cleanValue = value.split('?')[0].split('#')[0].trim();
  const lastSegment = cleanValue.split('/').pop() || cleanValue;
  const extension = lastSegment.includes('.') ? lastSegment.split('.').pop() : '';
  return extension.toLowerCase();
}

function getFileTypeFromExtension(ext) {
  if (!ext) return null;
  if (ext === 'pdf') return 'pdf';
  if (OFFICE_EXTENSIONS.includes(ext)) return 'office';
  if (IMAGE_EXTENSIONS.includes(ext)) return 'image';
  if (TEXT_EXTENSIONS.includes(ext)) return 'text';
  return 'download';
}

function getFileType({ filename, fileUrl, contentType, defaultPage, highlightBbox, onTextSelect }) {
  const typeFromFilename = getFileTypeFromExtension(getExtension(filename));
  if (typeFromFilename) return typeFromFilename;

  const typeFromUrl = getFileTypeFromExtension(getExtension(fileUrl));
  if (typeFromUrl) return typeFromUrl;

  if (contentType?.startsWith('image/')) return 'image';
  if (contentType?.startsWith('text/')) return 'text';
  if (contentType === 'application/pdf') return 'pdf';
  if (
    contentType &&
    [
      'application/msword',
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'application/vnd.ms-powerpoint',
      'application/vnd.openxmlformats-officedocument.presentationml.presentation',
      'application/vnd.ms-excel',
      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    ].includes(contentType)
  ) {
    return 'office';
  }

  if (defaultPage || highlightBbox || onTextSelect) return 'pdf';
  return 'pdf';
}

function OfficeViewer({ fileUrl, filename }) {
  const officeUrl = `https://view.officeapps.live.com/op/embed.aspx?src=${encodeURIComponent(fileUrl)}`;
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center px-2 py-1 border-b bg-muted/30 gap-2 shrink-0">
        <FileText className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-[11px] font-medium text-muted-foreground truncate">{filename}</span>
      </div>
      <iframe
        src={officeUrl}
        className="flex-1 w-full border-0"
        title={filename}
      />
    </div>
  );
}

function ImageViewer({ fileUrl, filename }) {
  const [loadFailed, setLoadFailed] = useState(false);

  if (loadFailed) {
    return <DownloadFallback fileUrl={fileUrl} filename={filename || 'image file'} />;
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center px-2 py-1 border-b bg-muted/30 gap-2 shrink-0">
        <FileText className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-[11px] font-medium text-muted-foreground truncate">{filename}</span>
      </div>
      <div className="flex-1 overflow-auto flex items-center justify-center p-4 bg-muted/20">
        <img
          src={fileUrl}
          alt={filename}
          className="max-w-full max-h-full object-contain shadow-md"
          onError={() => setLoadFailed(true)}
        />
      </div>
    </div>
  );
}

function TextViewer({ fileUrl, filename }) {
  const [text, setText] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setText(null);
    setError(null);
    fetch(fileUrl)
      .then((r) => r.text())
      .then(setText)
      .catch(() => setError('Failed to load file.'));
  }, [fileUrl]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center px-2 py-1 border-b bg-muted/30 gap-2 shrink-0">
        <FileText className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-[11px] font-medium text-muted-foreground truncate">{filename}</span>
      </div>
      <div className="flex-1 overflow-auto p-4 bg-muted/20">
        {!text && !error && (
          <div className="flex items-center justify-center h-full gap-2 text-muted-foreground">
            <Loader2 className="h-5 w-5 animate-spin" />
            <span className="text-sm">Loading…</span>
          </div>
        )}
        {error && <p className="text-sm text-destructive">{error}</p>}
        {text && <pre className="text-xs text-foreground whitespace-pre-wrap font-mono">{text}</pre>}
      </div>
    </div>
  );
}

function DownloadFallback({ fileUrl, filename }) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-3 p-8">
      <FileDown className="h-10 w-10 text-muted-foreground" />
      <p className="text-sm text-muted-foreground text-center">
        This file type cannot be previewed inline.
      </p>
      <a
        href={fileUrl}
        download={filename}
        className="text-sm font-medium text-primary hover:underline"
      >
        Download {filename}
      </a>
    </div>
  );
}

export default function DocumentViewer({
  fileUrl,
  pdfUrl,             // legacy alias
  filename = '',
  contentType,
  defaultPage,
  highlightBbox,
  onHighlightClick,
  onTextSelect,
  suppressDefaultPageScroll,
}) {
  const resolvedUrl = fileUrl || pdfUrl;
  const fileType = getFileType({
    filename,
    fileUrl: resolvedUrl,
    contentType,
    defaultPage,
    highlightBbox,
    onTextSelect,
  });

  if (!resolvedUrl) return null;

  if (fileType === 'pdf') {
    return (
      <PDFViewer
        pdfUrl={resolvedUrl}
        defaultPage={defaultPage}
        highlightBbox={highlightBbox}
        onHighlightClick={onHighlightClick}
        onTextSelect={onTextSelect}
        suppressDefaultPageScroll={suppressDefaultPageScroll}
      />
    );
  }

  if (fileType === 'office') {
    return <OfficeViewer fileUrl={resolvedUrl} filename={filename} />;
  }

  if (fileType === 'image') {
    return <ImageViewer fileUrl={resolvedUrl} filename={filename} />;
  }

  if (fileType === 'text') {
    return <TextViewer fileUrl={resolvedUrl} filename={filename} />;
  }

  return <DownloadFallback fileUrl={resolvedUrl} filename={filename} />;
}
