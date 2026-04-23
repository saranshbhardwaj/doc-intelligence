import { useEffect, useState } from "react";
import { loadDocumentPreview } from "@/utils/documentPreview";

export default function useDocumentPreview({ documentId, enabled = true, getToken }) {
  const [state, setState] = useState({
    isLoading: false,
    documentUrl: null,
    documentFilename: "",
    documentContentType: "",
    documentMissing: false,
    documentError: null,
  });

  useEffect(() => {
    if (!enabled || !documentId || !getToken) {
      setState({
        isLoading: false,
        documentUrl: null,
        documentFilename: "",
        documentContentType: "",
        documentMissing: false,
        documentError: null,
      });
      return undefined;
    }

    let cancelled = false;

    async function loadPreview() {
      setState((prev) => ({
        ...prev,
        isLoading: true,
        documentError: null,
        documentMissing: false,
      }));

      try {
        const preview = await loadDocumentPreview(getToken, documentId);
        if (cancelled) return;

        if (preview?.missing) {
          setState({
            isLoading: false,
            documentUrl: null,
            documentFilename: "",
            documentContentType: "",
            documentMissing: true,
            documentError: null,
          });
          return;
        }

        if (!preview?.url) {
          setState({
            isLoading: false,
            documentUrl: null,
            documentFilename: "",
            documentContentType: "",
            documentMissing: false,
            documentError: "Failed to load the source document.",
          });
          return;
        }

        setState({
          isLoading: false,
          documentUrl: preview.url,
          documentFilename: preview.filename || "",
          documentContentType: preview.contentType || "",
          documentMissing: false,
          documentError: null,
        });
      } catch (error) {
        if (cancelled) return;

        console.error("Failed to load source document", error);
        setState({
          isLoading: false,
          documentUrl: null,
          documentFilename: "",
          documentContentType: "",
          documentMissing: false,
          documentError: "Failed to load the source document.",
        });
      }
    }

    loadPreview();

    return () => {
      cancelled = true;
    };
  }, [documentId, enabled, getToken]);

  return state;
}