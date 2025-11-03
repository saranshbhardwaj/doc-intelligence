#!/usr/bin/env python3
"""Test LLM pipeline with saved chunks.

This script loads chunks from logs/chunks/ and runs them through the complete
LLM pipeline:
1. Load chunks
2. Summarize narrative chunks with cheap LLM (Haiku)
3. Combine summaries + tables
4. Extract structured data with expensive LLM (Sonnet)
5. Validate against ExtractedData model

Recovery points:
- If cheap LLM fails: Restart from step 2
- If expensive LLM fails: Use saved summaries from logs/summaries/, restart from step 4
- All intermediate outputs are saved for debugging

Usage:
    python scripts/test_llm_pipeline.py logs/chunks/2025-11-02_XX-XX-XX_CIM-06-Pizza-Hut_chunks.json

Options:
    --skip-cheap-llm    Skip cheap LLM and use raw narrative text (for testing)
    --use-saved-summaries logs/summaries/XXX_summaries.json
                        Use previously saved summaries instead of calling cheap LLM
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Dict
import importlib

# Add backend to path
backend_root = Path(__file__).parent.parent
sys.path.insert(0, str(backend_root))

# Load environment variables
from dotenv import load_dotenv
load_dotenv(backend_root / ".env")

# Force reload of summary_prompt to get latest changes
if 'app.services.summary_prompt' in sys.modules:
    import app.services.summary_prompt
    importlib.reload(app.services.summary_prompt)

from app.services.llm_client import LLMClient
from app.config import settings
from app.utils.logging import logger
from app.utils.file_utils import save_summaries, save_combined_context
from app.models import ExtractedData
from app.services.summary_prompt import SUMMARY_SYSTEM_PROMPT
from pydantic import ValidationError


def load_chunks(chunks_path: Path) -> tuple[list[dict], dict]:
    """Load chunks from JSON file."""
    with open(chunks_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    chunks = data.get("chunks", [])
    metadata = {
        "chunk_strategy": data.get("chunk_strategy"),
        "chunk_count": data.get("chunk_count"),
        "total_chars": data.get("total_chars"),
    }

    return chunks, metadata


def load_saved_summaries(summaries_path: Path) -> list[str]:
    """Load previously saved summaries."""
    with open(summaries_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    summaries_data = data.get("summaries", [])
    return [s["summary"] for s in summaries_data]


def separate_chunks(chunks: list[dict]) -> tuple[list[dict], list[dict]]:
    """Separate narrative-only chunks from chunks with tables."""
    narrative_chunks = []
    table_chunks = []

    for chunk in chunks:
        if chunk["metadata"].get("has_tables", False):
            table_chunks.append(chunk)
        else:
            narrative_chunks.append(chunk)

    return narrative_chunks, table_chunks


async def summarize_narrative_chunks(
    llm_client: LLMClient,
    narrative_chunks: list[dict],
    batch_size: int = 10
) -> list[str]:
    """Summarize narrative chunks using cheap LLM with batch processing."""
    summaries = []

    print(f"\n{'='*60}")
    print(f"STEP 2: Summarizing {len(narrative_chunks)} narrative chunks")
    print(f"{'='*60}")
    print(f"Model: {settings.cheap_llm_model}")
    print(f"Batch size: {batch_size}")
    print(f"\nSystem prompt (first 200 chars):")
    print(f"  {SUMMARY_SYSTEM_PROMPT[:200]}...")
    print(f"  Target compression: 40-60%")

    for i in range(0, len(narrative_chunks), batch_size):
        batch = narrative_chunks[i:i+batch_size]
        batch_num = i // batch_size + 1
        total_batches = (len(narrative_chunks) + batch_size - 1) // batch_size

        batch_data = [
            {"page": chunk["metadata"]["page_number"], "text": chunk["narrative_text"]}
            for chunk in batch
        ]

        print(f"\nBatch {batch_num}/{total_batches}: Summarizing pages {batch_data[0]['page']}-{batch_data[-1]['page']}")

        try:
            batch_summaries = await llm_client.summarize_chunks_batch(batch_data)
            summaries.extend(batch_summaries)
            print(f"  ✓ Received {len(batch_summaries)} summaries")
        except Exception as e:
            print(f"  ✗ Failed: {e}")
            # Fallback: use original text
            print(f"  ⚠ Falling back to original text")
            summaries.extend([chunk["narrative_text"] for chunk in batch])

    print(f"\n✓ Completed cheap LLM summarization")
    print(f"  Total summaries: {len(summaries)}")

    return summaries


def build_combined_context(
    narrative_chunks: list[dict],
    narrative_summaries: list[str],
    table_chunks: list[dict],
    total_chars: int
) -> tuple[str, dict]:
    """Build combined context for expensive LLM."""
    combined_sections = []

    # Add narrative summaries
    if narrative_summaries:
        combined_sections.append("=== DOCUMENT SUMMARIES (Narrative) ===\n")
        for i, chunk in enumerate(narrative_chunks):
            page_num = chunk["metadata"]["page_number"]
            summary = narrative_summaries[i] if i < len(narrative_summaries) else chunk["narrative_text"]
            combined_sections.append(f"[Page {page_num}]\n{summary}\n")

    # Add table chunks (raw, untouched)
    if table_chunks:
        combined_sections.append("\n=== FINANCIAL TABLES (Complete Data) ===\n")
        for chunk in table_chunks:
            page_num = chunk["metadata"]["page_number"]
            table_count = chunk["metadata"]["table_count"]
            combined_sections.append(
                f"[Page {page_num} - Contains {table_count} table(s)]\n{chunk['text']}\n"
            )

    combined_text = "\n".join(combined_sections)

    compression_ratio = (
        (1 - len(combined_text) / total_chars) * 100
        if total_chars > 0 else 0
    )

    metadata = {
        "original_chars": total_chars,
        "compressed_chars": len(combined_text),
        "compression_ratio": f"{compression_ratio:.1f}%",
        "narrative_chunks": len(narrative_chunks),
        "table_chunks": len(table_chunks),
        "narrative_summaries": len(narrative_summaries),
    }

    return combined_text, metadata


async def extract_with_expensive_llm(
    llm_client: LLMClient,
    combined_context: str
) -> dict:
    """Extract structured data with expensive LLM."""
    print(f"\n{'='*60}")
    print(f"STEP 4: Extracting structured data with expensive LLM")
    print(f"{'='*60}")
    print(f"Model: {settings.llm_model}")
    print(f"Input chars: {len(combined_context):,}")
    print(f"Max output tokens: {settings.llm_max_tokens}")

    try:
        extracted_data = llm_client.extract_structured_data(combined_context)
        print(f"\n✓ Extraction successful")
        return extracted_data
    except Exception as e:
        print(f"\n✗ Extraction failed: {e}")
        raise


def validate_extraction(extracted_data: dict) -> tuple[bool, list[str]]:
    """Validate extracted data against ExtractedData model."""
    print(f"\n{'='*60}")
    print(f"STEP 5: Validating against ExtractedData model")
    print(f"{'='*60}")

    try:
        validated = ExtractedData(**extracted_data)
        print(f"✓ Validation successful")

        # Print summary of what was extracted
        print(f"\nExtracted fields:")
        if validated.company_info and validated.company_info.company_name:
            print(f"  - Company: {validated.company_info.company_name}")
        if validated.financials:
            print(f"  - Revenue years: {list(validated.financials.revenue_by_year.keys())}")
        if validated.key_risks:
            print(f"  - Key risks: {len(validated.key_risks)}")
        if validated.management_team:
            print(f"  - Management team: {len(validated.management_team)}")

        return True, []
    except ValidationError as e:
        print(f"✗ Validation failed")
        errors = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
        for error in errors:
            print(f"  - {error}")
        return False, errors


async def main():
    parser = argparse.ArgumentParser(
        description="Test LLM pipeline with saved chunks"
    )
    parser.add_argument(
        "chunks_path",
        type=str,
        help="Path to chunks JSON file (from logs/chunks/)"
    )
    parser.add_argument(
        "--skip-cheap-llm",
        action="store_true",
        help="Skip cheap LLM and use raw narrative text"
    )
    parser.add_argument(
        "--use-saved-summaries",
        type=str,
        help="Use previously saved summaries instead of calling cheap LLM"
    )

    args = parser.parse_args()

    # Validate inputs
    chunks_path = Path(args.chunks_path)
    if not chunks_path.exists():
        print(f"Error: Chunks file not found: {chunks_path}")
        sys.exit(1)

    # Generate request ID for this test run
    request_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = chunks_path.stem.replace("_chunks", "")

    print(f"{'='*60}")
    print(f"LLM PIPELINE TEST")
    print(f"{'='*60}")
    print(f"Request ID: {request_id}")
    print(f"Chunks file: {chunks_path.name}")
    print(f"{'='*60}\n")

    # Step 1: Load chunks
    print(f"STEP 1: Loading chunks")
    print(f"{'='*60}")
    chunks, chunk_metadata = load_chunks(chunks_path)
    print(f"Loaded {len(chunks)} chunks")
    print(f"  Total chars: {chunk_metadata['total_chars']:,}")
    print(f"  Strategy: {chunk_metadata['chunk_strategy']}")

    # Separate narrative and table chunks
    narrative_chunks, table_chunks = separate_chunks(chunks)
    print(f"\nChunk breakdown:")
    print(f"  Narrative-only: {len(narrative_chunks)}")
    print(f"  With tables: {len(table_chunks)}")

    # Initialize LLM client
    llm_client = LLMClient(
        api_key=settings.anthropic_api_key,
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        max_input_chars=settings.llm_max_input_chars,
        timeout_seconds=settings.llm_timeout_seconds
    )

    # Step 2: Summarize narrative chunks (or skip/load saved)
    if args.use_saved_summaries:
        summaries_path = Path(args.use_saved_summaries)
        if not summaries_path.exists():
            print(f"Error: Summaries file not found: {summaries_path}")
            sys.exit(1)
        print(f"\nLoading saved summaries from: {summaries_path.name}")
        narrative_summaries = load_saved_summaries(summaries_path)
        print(f"✓ Loaded {len(narrative_summaries)} summaries")
    elif args.skip_cheap_llm:
        print(f"\n⚠ Skipping cheap LLM (using raw narrative text)")
        narrative_summaries = [chunk["narrative_text"] for chunk in narrative_chunks]
    else:
        narrative_summaries = await summarize_narrative_chunks(
            llm_client,
            narrative_chunks,
            batch_size=settings.chunk_batch_size
        )

        # Save summaries for recovery
        save_summaries(
            request_id,
            {
                "model": settings.cheap_llm_model,
                "total_summaries": len(narrative_summaries),
                "batch_size": settings.chunk_batch_size,
                "summaries": [
                    {
                        "page": narrative_chunks[i]["metadata"]["page_number"],
                        "original_chars": len(narrative_chunks[i]["narrative_text"]),
                        "summary": summary
                    }
                    for i, summary in enumerate(narrative_summaries)
                ]
            },
            filename
        )
        print(f"\n✓ Summaries saved to logs/summaries/{request_id}_*_summaries.json")

    # Step 3: Build combined context
    print(f"\n{'='*60}")
    print(f"STEP 3: Building combined context")
    print(f"{'='*60}")

    combined_context, context_metadata = build_combined_context(
        narrative_chunks,
        narrative_summaries,
        table_chunks,
        chunk_metadata["total_chars"]
    )

    print(f"Combined context stats:")
    print(f"  Original: {context_metadata['original_chars']:,} chars")
    print(f"  Compressed: {context_metadata['compressed_chars']:,} chars")
    print(f"  Compression: {context_metadata['compression_ratio']}")

    # Save combined context for recovery
    save_combined_context(request_id, combined_context, context_metadata, filename)
    print(f"\n✓ Combined context saved to logs/combined/{request_id}_*_context.txt")

    # Step 4: Extract with expensive LLM
    try:
        extracted_data = await extract_with_expensive_llm(llm_client, combined_context)
    except Exception as e:
        print(f"\n❌ Pipeline failed at expensive LLM step")
        print(f"\nRecovery: You can retry by loading saved summaries:")
        print(f"  python scripts/test_llm_pipeline.py {chunks_path} \\")
        print(f"    --use-saved-summaries logs/summaries/{request_id}_*_summaries.json")
        sys.exit(1)

    # Step 5: Validate against model
    is_valid, errors = validate_extraction(extracted_data)

    # Save final result
    output_dir = Path("logs/test_results")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{request_id}_{filename}_result.json"

    result = {
        "request_id": request_id,
        "chunks_file": str(chunks_path),
        "timestamp": datetime.now().isoformat(),
        "validation_passed": is_valid,
        "validation_errors": errors,
        "extracted_data": extracted_data,
        "pipeline_metadata": {
            "chunk_metadata": chunk_metadata,
            "context_metadata": context_metadata,
            "narrative_chunks": len(narrative_chunks),
            "table_chunks": len(table_chunks),
            "cheap_llm_model": settings.cheap_llm_model,
            "expensive_llm_model": settings.llm_model,
        }
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"PIPELINE COMPLETE")
    print(f"{'='*60}")
    print(f"✓ Result saved to: {output_path}")
    print(f"✓ Validation: {'PASSED' if is_valid else 'FAILED'}")

    if not is_valid:
        print(f"\n⚠ Validation errors found - check result file for details")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
