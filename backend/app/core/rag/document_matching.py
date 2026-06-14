"""Document matching helpers for comparison queries."""
from __future__ import annotations

from typing import List, Dict, Optional
import difflib
import re
from app.repositories.document_repository import DocumentRepository
from app.utils.logging import logger


_MATCH_NORMALIZATION_PATTERNS = (
    (re.compile(r"\bst\.?\b", re.IGNORECASE), "street"),
    (re.compile(r"\bave\.?\b", re.IGNORECASE), "avenue"),
    (re.compile(r"\bblvd\.?\b", re.IGNORECASE), "boulevard"),
    (re.compile(r"\brd\.?\b", re.IGNORECASE), "road"),
    (re.compile(r"\bdr\.?\b", re.IGNORECASE), "drive"),
    (re.compile(r"\bln\.?\b", re.IGNORECASE), "lane"),
    (re.compile(r"\bct\.?\b", re.IGNORECASE), "court"),
    (re.compile(r"\bpkwy\.?\b", re.IGNORECASE), "parkway"),
)


def _normalize_match_text(value: str) -> str:
    text = (value or "").lower().strip()
    if not text:
        return ""

    text = text.replace("&", " and ")
    text = re.sub(r"[_\-/]+", " ", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    for pattern, replacement in _MATCH_NORMALIZATION_PATTERNS:
        text = pattern.sub(replacement, text)
    return re.sub(r"\s+", " ", text).strip()


class DocumentMatcher:
    def __init__(self, db):
        self.db = db
        self.document_repo = DocumentRepository()

    def match_entities_to_documents(
        self,
        entities: List,
        documents: List[Dict]
    ) -> List[str]:
        matched_ids = []
        doc_entities = [e for e in entities if e.entity_type == "document"]

        for entity in doc_entities:
            match = self.fuzzy_match_document(entity.name, documents, threshold=0.5)
            if match and match["id"] not in matched_ids:
                matched_ids.append(match["id"])
                logger.debug(
                    f"Matched entity '{entity.name}' to document '{match['filename']}'",
                    extra={"entity": entity.name, "matched_filename": match["filename"]}
                )

        return matched_ids

    def match_entities_with_scores(
        self,
        entities: List,
        documents: List[Dict]
    ) -> List[Dict]:
        """
        Like match_entities_to_documents but returns score alongside each match.

        Returns [{id, filename, score}] for document entities with score >= 0.65.
        Used by callers that need confidence-gated filtering (e.g. document-scoped retrieval).
        """
        results = []
        seen_ids: set = set()
        doc_entities = [e for e in entities if e.entity_type == "document"]

        for entity in doc_entities:
            extracted_clean = entity.name.lower().strip()
            best_match = None
            best_score = 0.0

            for doc in documents:
                score = self._score_document_match(extracted_clean, doc)
                if score > best_score:
                    best_score = score
                    best_match = doc

            if best_match and best_score >= 0.65 and best_match["id"] not in seen_ids:
                results.append({
                    "id": best_match["id"],
                    "filename": best_match["filename"],
                    "score": best_score,
                })
                seen_ids.add(best_match["id"])
                logger.debug(
                    f"match_entities_with_scores: '{entity.name}' → '{best_match['filename']}' (score={best_score:.2f})",
                    extra={"entity": entity.name, "matched_filename": best_match["filename"], "score": best_score}
                )

        return results

    def filter_documents_by_query(
        self,
        user_message: str,
        document_ids: List[str]
    ) -> Optional[List[str]]:
        if not document_ids:
            return None

        documents = []
        for doc_id in document_ids:
            doc = self.document_repo.get_by_id(doc_id)
            if doc:
                documents.append({
                    "id": doc.id,
                    "filename": doc.filename
                })

        if not documents:
            return None

        extracted_names = self.extract_document_names(user_message)
        if not extracted_names:
            return None

        logger.info(
            f"Extracted document names from query: {extracted_names}",
            extra={"query": user_message[:100], "extracted": extracted_names}
        )

        matched_ids = []
        for extracted in extracted_names:
            best_match = self.fuzzy_match_document(extracted, documents)
            if best_match:
                matched_ids.append(best_match["id"])
                logger.debug(
                    f"Matched '{extracted}' to '{best_match['filename']}'",
                    extra={"extracted": extracted, "matched": best_match["filename"]}
                )

        if matched_ids:
            logger.info(
                f"Filtered {len(document_ids)} documents to {len(matched_ids)} based on query mentions",
                extra={"total": len(document_ids), "filtered": len(matched_ids)}
            )
            return matched_ids

        logger.warning(
            "Extracted document names but no good matches found, using all documents",
            extra={"extracted": extracted_names, "num_docs": len(documents)}
        )
        return None

    def extract_document_names(self, query: str) -> List[str]:
        query_lower = query.lower()
        extracted = []

        match = re.search(r"compare\s+([^,]+?)\s+(?:and|with)\s+([^,\.]+)", query_lower)
        if match:
            extracted.extend([match.group(1).strip(), match.group(2).strip()])

        match = re.search(r"([^,\s]+)\s+(?:vs\.?|versus)\s+([^,\.]+)", query_lower)
        if match:
            extracted.extend([match.group(1).strip(), match.group(2).strip()])

        match = re.search(r"between\s+([^,]+?)\s+and\s+([^,\.]+)", query_lower)
        if match:
            extracted.extend([match.group(1).strip(), match.group(2).strip()])

        if not extracted:
            match = re.search(r"([^,]+),\s*([^,]+?)\s+and\s+([^,\.]+)", query_lower)
            if match:
                extracted.extend([
                    match.group(1).strip(),
                    match.group(2).strip(),
                    match.group(3).strip()
                ])

        stop_words = {"these", "those", "documents", "files", "properties", "deals", "the", "document", "file", "property", "deal"}
        extracted = [name for name in extracted if name not in stop_words]

        return extracted

    def fuzzy_match_document(
        self,
        extracted_name: str,
        documents: List[Dict[str, str]],
        threshold: float = 0.6
    ) -> Optional[Dict[str, str]]:
        extracted_clean = extracted_name.lower().strip()
        best_match = None
        best_score = 0.0

        for doc in documents:
            score = self._score_document_match(extracted_clean, doc)

            if score > best_score:
                best_score = score
                best_match = doc

        if best_score >= threshold:
            return best_match
        return None

    def _score_document_match(self, extracted_clean: str, doc: Dict[str, str]) -> float:
        filename = doc["filename"]
        filename_no_ext = filename.rsplit(".", 1)[0] if "." in filename else filename

        extracted_normalized = _normalize_match_text(extracted_clean)
        candidates = [filename_no_ext.lower().strip(), filename.lower().strip()]

        for alias in doc.get("aliases", []) or []:
            if isinstance(alias, str) and alias.strip():
                candidates.append(alias.lower().strip())

        scope_text = (doc.get("scope_text") or "").lower().strip()
        if scope_text:
            candidates.append(scope_text)

        best_score = 0.0
        for candidate in candidates:
            if not candidate:
                continue
            candidate_normalized = _normalize_match_text(candidate)
            score = difflib.SequenceMatcher(None, extracted_normalized, candidate_normalized).ratio()
            if extracted_normalized in candidate_normalized or candidate_normalized in extracted_normalized:
                score = max(score, 0.8)
            best_score = max(best_score, score)

        return best_score
