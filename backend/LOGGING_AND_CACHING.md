# Logging and Caching Strategy

This document explains what is logged/cached at each stage of the multi-stage LLM processing pipeline.

## Pipeline Overview

```
User Upload PDF
    ↓
[Cache Check] → If HIT, return cached result
    ↓ (cache miss)
[Parse] → Azure/Google/LLMWhisperer
    ↓
[Chunk] → Page-wise or semantic chunking
    ↓
[Summarize] → Cheap LLM (Haiku) processes narrative
    ↓
[Combine] → Summaries + raw tables
    ↓
[Extract] → Expensive LLM (Sonnet) structured extraction
    ↓
[Cache & Return] → Store result, return to user
```

---

## Logging at Each Stage

### Stage 1: Parse
**What happens:** Parser extracts text and tables from PDF

**Logged:**
- `logs/raw/[timestamp]_[file]_[id].txt` - Full extracted text
- `logs/azure_raw/[timestamp]_[file]_[id].json` - Complete Azure response (for Azure parser)

**Why:**
- Debug parser output quality
- Verify table extraction
- Re-chunk without re-parsing (saves API costs)

**Production note:** ✅ Keep enabled (helps debug parser issues)

---

### Stage 2: Chunk
**What happens:** Parser output split into processable chunks (page-wise, semantic, etc.)

**Logged:**
- `logs/chunks/[timestamp]_[file]_chunks.json`

**Format:**
```json
{
  "strategy": "page_wise",
  "total_chunks": 30,
  "metadata": {
    "total_chars": 45000,
    "narrative_chars": 37500,
    "pages_with_tables": 5
  },
  "chunks": [
    {
      "chunk_id": "page_1",
      "text": "First 500 chars preview...",
      "metadata": {
        "page_number": 1,
        "has_tables": false,
        "char_count": 1500
      }
    }
  ]
}
```

**Why:**
- Verify chunking strategy effectiveness
- Debug chunk boundaries
- Compare different chunking strategies

**Production note:** ✅ Keep enabled in development, ⚠️ optional in production (can generate large files)

---

### Stage 3: Summarize (Cheap LLM)
**What happens:** Haiku summarizes narrative chunks, preserving numbers/facts

**Logged:**
- `logs/summaries/[timestamp]_[file]_summaries.json`

**Format:**
```json
{
  "model": "claude-haiku-3-5-20241022",
  "total_summaries": 25,
  "batch_size": 10,
  "summaries": [
    {
      "page": 1,
      "original_chars": 1500,
      "summary": "Company operates 450+ locations in Western US. Revenue $87.3M..."
    }
  ]
}
```

**Why:**
- Verify summarization quality (are numbers preserved?)
- Debug cheap LLM failures
- Compare summary compression ratios

**Production note:** ✅ Keep enabled (critical for verifying data preservation)

---

### Stage 4: Combine Context
**What happens:** Narrative summaries + raw tables combined for expensive LLM

**Logged:**
- `logs/combined/[timestamp]_[file]_context.txt` - Actual text sent to expensive LLM
- `logs/combined/[timestamp]_[file]_metadata.json` - Compression stats

**Text format:**
```
=== DOCUMENT SUMMARIES (Narrative) ===

[Page 1]
Company operates 450+ locations. Revenue $87.3M (2021) to $102.5M (2022)...

[Page 2]
Management team has 50+ years combined experience...

=== FINANCIAL TABLES (Complete Data) ===

[Page 5 - Contains 2 table(s)]
Year    Revenue    EBITDA
2021    $87.3M     $19.2M
2022    $102.5M    $22.3M
```

**Metadata:**
```json
{
  "original_chars": 45000,
  "compressed_chars": 18000,
  "compression_ratio": "60.0%",
  "narrative_chunks": 25,
  "table_chunks": 5,
  "narrative_summaries": 25
}
```

**Why:**
- See exactly what expensive LLM receives
- Verify tables aren't corrupted
- Debug extraction issues

**Production note:** ✅ Keep enabled (most valuable for debugging expensive LLM failures)

---

### Stage 5: Extract (Expensive LLM)
**What happens:** Sonnet performs structured extraction

**Logged:**
- `logs/raw_llm_response/[timestamp]_[file]_[id].json` - Raw JSON response from Sonnet
- `logs/parsed/[timestamp]_[file]_[id].json` - Normalized/validated extraction result

**Why:**
- Debug extraction failures
- Verify JSON schema compliance
- Track model performance

**Production note:** ✅ Keep enabled (already exists, essential for debugging)

---

## Caching Strategy

### Current: Final Result Caching ✅
**Cache key:** `hash(file_content)`
**Cached data:** Complete `ExtractedData` (final JSON result)
**TTL:** 48 hours (configurable)

**Location:** `logs/cache/`

**Hit rate:** High for re-uploads of same document

**Benefits:**
- ✅ Instant response for duplicate uploads
- ✅ Saves entire pipeline cost
- ✅ No rate limit impact on cache hits

---

### Future: Multi-Level Caching (Optional)

#### Level 1: Parser Output Cache
**Cache key:** `hash(file_content) + parser_name`
**Cached data:** `ParserOutput` (text + metadata)
**TTL:** 7 days

**When useful:**
- Testing different chunking strategies
- Comparing cheap LLM models
- Avoiding re-parsing during development

**Implementation:**
```python
parser_cache_key = f"{file_hash}_{parser_name}"
if parser_cache_key in parser_cache:
    parser_output = parser_cache[parser_cache_key]
else:
    parser_output = await parser.parse(...)
    parser_cache[parser_cache_key] = parser_output
```

**Recommendation:** 🔶 Optional (useful for development, not critical for production)

---

#### Level 2: Summary Cache
**Cache key:** `hash(chunks) + cheap_llm_model`
**Cached data:** List of summaries
**TTL:** 7 days

**When useful:**
- Testing different expensive LLM prompts
- A/B testing extraction strategies
- Quick iteration on extraction logic

**Implementation:**
```python
chunks_hash = hash(json.dumps([c.chunk_id for c in chunks]))
summary_cache_key = f"{chunks_hash}_{cheap_llm_model}"

if summary_cache_key in summary_cache:
    summaries = summary_cache[summary_cache_key]
else:
    summaries = await llm_client.summarize_chunks_batch(...)
    summary_cache[summary_cache_key] = summaries
```

**Recommendation:** 🔶 Optional (nice-to-have for development)

---

## Disk Space Management

### Expected Storage Per Document

| Stage | File Size | Retention |
|-------|-----------|-----------|
| Raw text | ~50-150KB | 7 days |
| Azure JSON | ~200-500KB | 30 days (for re-chunking) |
| Chunks | ~100-300KB | 7 days |
| Summaries | ~20-50KB | 7 days |
| Combined context | ~30-80KB | 7 days |
| LLM response | ~50-100KB | 30 days |
| **Total per doc** | **~450KB-1.2MB** | - |

### For 1000 documents/month:
- Storage: ~450MB-1.2GB/month
- With 30-day retention: ~1.3GB-3.6GB total

**Cleanup strategy:** Automatic cleanup after TTL (implement cron job)

---

## What to Monitor in Production

### Critical Logs (Always Enable)
1. ✅ **Combined context** (`logs/combined/`) - Debug expensive LLM issues
2. ✅ **Summaries** (`logs/summaries/`) - Verify cheap LLM quality
3. ✅ **LLM responses** (`logs/raw_llm_response/`) - Track extraction failures

### Optional Logs (Development Only)
1. ⚠️ **Chunks** (`logs/chunks/`) - Large files, only needed when tuning chunking
2. ⚠️ **Raw text** (`logs/raw/`) - Already in cache, redundant

### Metrics to Track
```python
# In your analytics/monitoring
{
    "chunking_enabled": True,
    "compression_ratio": "60%",
    "cheap_llm_cost": "$0.03",
    "expensive_llm_cost": "$1.20",
    "total_cost": "$1.23",
    "cost_savings_vs_baseline": "18%",
    "processing_time_ms": 15000
}
```

---

## Configuration

### Enable/Disable Logging (`.env`)

```bash
# Chunking pipeline
ENABLE_CHUNKING=true

# Logging (future feature - for now all enabled by default)
LOG_CHUNKS=true          # logs/chunks/
LOG_SUMMARIES=true       # logs/summaries/
LOG_COMBINED=true        # logs/combined/

# Cache TTL
CACHE_TTL=48  # hours
```

---

## Testing Your Logs

### 1. Upload a test PDF
```bash
curl -X POST http://localhost:8000/api/extract \
  -F "file=@tests/data/sample_cims/CIM-06-Pizza-Hut.pdf"
```

### 2. Check generated logs
```bash
# See all logs for this request
ls -lh logs/chunks/2025-*
ls -lh logs/summaries/2025-*
ls -lh logs/combined/2025-*

# View combined context (what expensive LLM sees)
cat logs/combined/2025-*_context.txt

# View summaries (verify numbers preserved)
cat logs/summaries/2025-*_summaries.json | jq '.summaries[0]'
```

### 3. Verify compression
```bash
# Check metadata
cat logs/combined/2025-*_metadata.json | jq '.'
```

Expected output:
```json
{
  "original_chars": 45000,
  "compressed_chars": 18000,
  "compression_ratio": "60.0%",
  "narrative_chunks": 25,
  "table_chunks": 5
}
```

---

## Summary

### What You Get
- ✅ Complete visibility into multi-stage pipeline
- ✅ Debug each LLM call independently
- ✅ Verify data preservation (numbers in tables)
- ✅ Track cost savings from chunking
- ✅ Fast cache hits on duplicate uploads

### Storage Cost
- ~1MB per processed document
- ~3-4GB for 1000 docs/month with 30-day retention
- Negligible compared to LLM API costs

### Production Recommendation
1. ✅ Enable all logging initially (observe real-world data)
2. ⚠️ After 1 month, disable `logs/chunks/` (largest files)
3. ✅ Keep `logs/combined/` and `logs/summaries/` (most valuable)
4. ✅ Set up automated cleanup (delete logs >30 days old)
