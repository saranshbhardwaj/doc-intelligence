"""Standalone script to parse a PDF with Azure Document Intelligence and persist outputs.

Usage (from backend directory):
    python scripts/azure_parse_test.py /path/to/document.pdf [--model prebuilt-layout] [--timeout 180]

Environment variables required:
    AZURE_DOC_INTELLIGENCE_API_KEY
    AZURE_DOC_INTELLIGENCE_ENDPOINT

Outputs:
    - logs/azure_raw/<timestamp>_<filename>_<id>.json  (Full Azure response structure)
    - logs/raw/<timestamp>_<filename>_<id>.txt         (Combined text)
    - Console summary of pages, tables, cost.
"""
import argparse
import json
import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(backend_root))
load_dotenv(backend_root / ".env")

from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult, AnalyzeDocumentRequest
from azure.core.exceptions import AzureError

from app.config import settings  # ensures .env is loaded
from app.utils.file_utils import save_raw_text, save_raw_azure_output, make_file_label
from app.utils.logging import logger


def extract_structured(result: AnalyzeResult):
    """Build structured representation: pages with lines/words and tables with cells."""
    pages_out = []
    # Pre-build table index by page
    tables_by_page: dict[int, list] = {}
    for table in (result.tables or []):
        if not table.bounding_regions:
            continue
        page_num = table.bounding_regions[0].page_number
        tables_by_page.setdefault(page_num, []).append(table)

    for page in result.pages:
        line_texts = [ln.content for ln in getattr(page, "lines", []) or []]
        # Words might be large; include limited fields
        word_items = [
            {
                "content": w.content,
                "bounding_box": getattr(w, "polygon", None),
            }
            for w in getattr(page, "words", []) or []
        ]
        page_tables = []
        for table in tables_by_page.get(page.page_number, []):
            cells = [
                {
                    "rowIndex": c.row_index,
                    "columnIndex": c.column_index,
                    "content": c.content,
                    "kind": getattr(c, "kind", None),
                    "spans": [
                        {"offset": s.offset, "length": s.length} for s in getattr(c, "spans", []) or []
                    ],
                }
                for c in table.cells
            ]
            page_tables.append(
                {
                    "rowCount": table.row_count,
                    "columnCount": table.column_count,
                    "cells": cells,
                }
            )
        combined_text = "\n".join(line_texts)
        # Append rendered tables as plain text for backward compatibility
        for t in page_tables:
            # Reconstruct matrix text
            matrix = [["" for _ in range(t["columnCount"])] for _ in range(t["rowCount"])]
            for cell in t["cells"]:
                matrix[cell["rowIndex"]][cell["columnIndex"]] = cell["content"]
            rendered_rows = ["\t".join(r) for r in matrix]
            combined_text += "\n\n[Table]\n" + "\n".join(rendered_rows)

        pages_out.append(
            {
                "page_number": page.page_number,
                "width": getattr(page, "width", None),
                "height": getattr(page, "height", None),
                "unit": getattr(page, "unit", None),
                "lines": line_texts,
                "words": word_items[:500],  # cap words to avoid huge JSON
                "tables": page_tables,
                "text": combined_text.strip(),
                "char_count": len(combined_text.strip()),
                "table_count": len(page_tables),
            }
        )
    return pages_out


def main():
    parser = argparse.ArgumentParser(description="Test Azure Document Intelligence parsing.")
    parser.add_argument("pdf_path", type=str, help="Path to PDF file")
    parser.add_argument("--model", type=str, default=settings.azure_doc_model or "prebuilt-layout", help="Model ID")
    parser.add_argument("--timeout", type=int, default=settings.azure_doc_timeout_seconds or 180, help="Timeout seconds")
    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        print(f"File not found: {pdf_path}")
        sys.exit(1)

    endpoint = settings.azure_doc_intelligence_endpoint or os.getenv("AZURE_DOC_INTELLIGENCE_ENDPOINT")
    api_key = settings.azure_doc_intelligence_api_key or os.getenv("AZURE_DOC_INTELLIGENCE_API_KEY")

    if not endpoint or not api_key:
        print("Azure endpoint/api key missing. Set in .env or environment variables.")
        sys.exit(1)

    client = DocumentIntelligenceClient(endpoint=endpoint, credential=AzureKeyCredential(api_key))
    request_id = uuid.uuid4().hex[:12]
    file_label = make_file_label(pdf_path.name, request_id)
    logger.info("Starting Azure parse test", extra={"file": str(pdf_path), "model": args.model, "request_id": request_id})

    try:
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        analyze_request = AnalyzeDocumentRequest(bytes_source=pdf_bytes)
        poller = client.begin_analyze_document(model_id=args.model, body=analyze_request)
        result: AnalyzeResult = poller.result(timeout=args.timeout)
    except TimeoutError:
        logger.error(f"Timeout after {args.timeout}s", extra={"request_id": request_id})
        print(f"Timeout after {args.timeout}s")
        sys.exit(2)
    except AzureError as e:
        logger.error(f"Azure error: {e}", extra={"request_id": request_id, "error_type": type(e).__name__})
        print(f"Azure API error: {e}")
        sys.exit(3)
    except Exception as e:
        logger.exception("Unexpected failure", extra={"request_id": request_id})
        print(f"Unexpected error: {e}")
        sys.exit(4)

    pages = extract_structured(result)
    full_text = "\n\n".join(p["text"] for p in pages)
    total_chars = len(full_text)
    page_count = len(pages)
    cost_usd = page_count * 0.01  # $0.01/page

    # Prepare raw Azure JSON (serialize result safely)
    # result.to_dict() exists in some SDKs; fallback to manual attrs if not.
    try:
        raw_dict = result.to_dict()  # type: ignore[attr-defined]
    except AttributeError:
        # Minimal manual extraction if to_dict not available
        raw_dict = {
            "model_id": args.model,
            "pages": [
                {
                    "page_number": p.page_number,
                    "width": getattr(p, "width", None),
                    "height": getattr(p, "height", None),
                    "unit": getattr(p, "unit", None),
                    "line_count": len(getattr(p, "lines", []) or []),
                } for p in result.pages
            ],
            "table_count": len(result.tables or []),
        }

    # Compose analyzeResult-like structure matching Azure Studio visualization expectations
    analyze_result_like = {
        "status": "succeeded",
        "createdDateTime": None,  # Not available from SDK object directly
        "lastUpdatedDateTime": None,
        "analyzeResult": {
            "apiVersion": getattr(result, "api_version", None),
            "modelId": getattr(result, "model_id", None) or args.model,
            "stringIndexType": "utf16CodeUnit",  # default assumption
            "content": full_text,  # full concatenated content
            "pages": [
                {
                    "pageNumber": p["page_number"],
                    "unit": p.get("unit"),
                    "width": p.get("width"),
                    "height": p.get("height"),
                    "lines": [
                        {"content": ln} for ln in p.get("lines", [])
                    ],
                    "words": p.get("words", []),
                    "tables": p.get("tables", []),
                    "tableCount": p.get("table_count", 0),
                    "charCount": p.get("char_count", 0),
                }
                for p in pages
            ],
            "tables": [
                {
                    "pageNumber": (t.bounding_regions[0].page_number if t.bounding_regions else None),
                    "rowCount": t.row_count,
                    "columnCount": t.column_count,
                    "cells": [
                        {
                            "rowIndex": c.row_index,
                            "columnIndex": c.column_index,
                            "content": c.content,
                            "kind": getattr(c, "kind", None),
                            "spans": [
                                {"offset": s.offset, "length": s.length} for s in getattr(c, "spans", []) or []
                            ],
                        }
                        for c in t.cells
                    ],
                }
                for t in (result.tables or [])
            ],
            "paragraphs": [],  # Could be populated if needed with result.paragraphs
            "keyValuePairs": [],  # Add if using prebuilt forms model
            "styles": [],  # style info if available
        },
        "summary": {
            "page_count": page_count,
            "total_chars": total_chars,
            "avg_chars_per_page": total_chars / page_count if page_count else 0,
            "total_tables": sum(p["table_count"] for p in pages),
            "cost_usd": cost_usd,
            "model": args.model,
        },
        "raw": raw_dict,
    }

    save_raw_azure_output(request_id, analyze_result_like, pdf_path.name)

    save_raw_text(request_id, full_text, pdf_path.name)

    print("--- Azure Parse Summary ---")
    print(f"Request ID: {request_id}")
    print(f"File: {pdf_path.name}")
    print(f"Pages: {page_count}")
    print(f"Characters: {total_chars}")
    print(f"Tables: {sum(p['table_count'] for p in pages)}")
    print(f"Cost (est): ${cost_usd:.2f}")
    print(f"Output saved under logs/azure_raw and logs/raw")

    # Optional: print first 300 chars as preview
    preview = full_text[:300].replace("\n", " ")
    print(f"Preview: {preview}...")


if __name__ == "__main__":
    main()
