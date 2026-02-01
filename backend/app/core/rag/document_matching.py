"""Document matching helpers for comparison queries."""
from __future__ import annotations

from typing import List, Dict, Optional
import difflib
import re
from app.repositories.document_repository import DocumentRepository
from app.utils.logging import logger


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
            filename = doc["filename"]
            filename_no_ext = filename.rsplit(".", 1)[0] if "." in filename else filename
            filename_clean = filename_no_ext.lower().strip()

            score1 = difflib.SequenceMatcher(None, extracted_clean, filename_clean).ratio()
            score2 = difflib.SequenceMatcher(None, extracted_clean, doc["filename"].lower()).ratio()
            score = max(score1, score2)

            if extracted_clean in filename_clean or filename_clean in extracted_clean:
                score = max(score, 0.8)

            if score > best_score:
                best_score = score
                best_match = doc

        if best_score >= threshold:
            return best_match
        return None
