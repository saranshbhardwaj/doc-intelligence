# Re-ranker & Compression Implementation

## Overview

Enhanced RAG pipeline with cross-encoder re-ranking and intelligent chunk compression for token limit handling.

## Architecture

```
Query
  ↓
[1] Hybrid Retrieval (20 candidates)
    - Semantic search (pgvector)
    - Keyword search (PostgreSQL FTS)
    - Query-adaptive metadata boosting (stronger)
  ↓
[2] Re-ranking (Top 10)
    - Optional: Chunk compression (if > 512 tokens)
    - Cross-encoder scoring
    - Metadata boosting (gentler nudge)
  ↓
[3] Budget Enforcement
  ↓
[4] LLM Context
```

## New Files Created

### 1. `metadata_booster.py`
**Shared utility for metadata-based boosting**

- **Hybrid Retriever**: Stronger boosts (1.2x tables, 0.9x narrative for data queries)
- **Re-ranker**: Gentler nudges (1.1x tables, 0.95x narrative for data queries)
- Factory methods: `MetadataBooster.for_hybrid_retriever()` and `MetadataBooster.for_reranker()`

### 2. `chunk_compressor.py`
**Handles chunks exceeding 512 token limit**

**Strategy:**
1. Count tokens with tiktoken
2. If ≤ 512 tokens → use as-is
3. If > 512 tokens:
   - **Tabular chunks**: Smart truncation (head_tail strategy)
   - **Narrative chunks**: LLMLingua-2 compression → fallback to truncation if needed

**Truncation strategies:**
- `head_tail`: Keep first 60% + last 40% of tokens (default)
- `head`: Keep first N tokens
- `tail`: Keep last N tokens

**Features:**
- Preserves section headings
- Tracks compression metrics (ratio, method)
- Can be toggled on/off via config

### 3. `reranker.py`
**Cross-encoder based re-ranking**

**Features:**
- Uses `cross-encoder/ms-marco-MiniLM-L-6-v2` by default
- Optional chunk compression before re-ranking
- Optional metadata boosting (gentle nudge for tables)
- Batch processing for efficiency
- Fallback to hybrid scores on error

## Configuration

### New Settings in `config.py`

```python
# Re-ranker Settings
rag_use_reranker: bool = True  # Enable/disable re-ranker
rag_reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
rag_reranker_batch_size: int = 8
rag_reranker_token_limit: int = 512
rag_reranker_apply_metadata_boost: bool = True  # Gentle table boosting

# Compression Settings
rag_use_compression: bool = True  # Enable/disable compression
rag_compression_model: str = "microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank"
rag_compression_rate: float = 0.5  # 50% compression
rag_truncation_strategy: str = "head_tail"  # "head_tail", "head", or "tail"
rag_preserve_headings: bool = True

# Retrieval Settings
rag_retrieval_candidates: int = 20  # Candidates for re-ranking
rag_final_top_k: int = 10  # Final chunks after re-ranking
```

## A/B Testing Guide

### Test 1: Re-ranker On/Off
```python
# In .env or config
rag_use_reranker=True   # With re-ranker
rag_use_reranker=False  # Without re-ranker (hybrid only)
```

### Test 2: Compression On/Off
```python
# With compression
rag_use_compression=True

# Without compression (truncation only)
rag_use_compression=False
```

### Test 3: Metadata Boosting in Re-ranker
```python
# With metadata boosting (gentle table preference)
rag_reranker_apply_metadata_boost=True

# Without boosting (trust cross-encoder only)
rag_reranker_apply_metadata_boost=False
```

### Test 4: Different Cross-Encoder Models
```python
# Fast, good quality
rag_reranker_model="cross-encoder/ms-marco-MiniLM-L-6-v2"

# Better quality, slower
rag_reranker_model="BAAI/bge-reranker-base"

# Best quality, slowest
rag_reranker_model="BAAI/bge-reranker-large"
```

## Installation

```bash
cd backend
pip install -r requirements.txt
```

**New dependencies:**
- `tiktoken==0.8.0` - Token counting
- `llmlingua==0.2.2` - Prompt compression
- `sentence-transformers==3.3.1` - Already installed (includes cross-encoders)

## Usage

The re-ranker is automatically integrated into `RAGService.chat()`. No code changes needed to use it.

```python
# Existing code works as-is
rag_service = RAGService(db)
async for chunk in rag_service.chat(
    session_id=session_id,
    collection_id=collection_id,
    user_message="What were the revenue numbers?"
):
    print(chunk, end="")
```

## Pipeline Flow

### Example: Data Query "What were Q3 revenue numbers?"

**Step 1: Hybrid Retrieval (20 candidates)**
- Query analysis: `query_type = "data_query"`
- Semantic search: 20 results
- Keyword search: 20 results
- Merge + metadata boost (tables get 1.2x, narrative gets 0.9x)
- → 20 unique candidates

**Step 2: Re-ranking (Top 10)**
- Compression: Long chunks → compress to ≤512 tokens
- Cross-encoder: Score each (query, chunk) pair
- Metadata boost: Gentle nudge (tables get 1.1x, narrative gets 0.95x)
- Sort by rerank_score
- → Top 10 chunks

**Step 3: Budget Enforcement**
- Trim context to fit LLM limits

**Step 4: LLM Response**
- Build prompt with top 10 chunks
- Stream response from Claude

## Boosting Strategy

### Why Two-Stage Boosting?

1. **Hybrid Retrieval Boosting** (Stronger)
   - Purpose: Candidate selection
   - Effect: Ensures important tables make it into top 20
   - Weights: 1.2x tables, 0.9x narrative (for data queries)

2. **Re-ranker Boosting** (Gentler)
   - Purpose: Final ranking refinement
   - Effect: Gentle nudge to preserve domain knowledge
   - Weights: 1.1x tables, 0.95x narrative (for data queries)
   - Rationale: Cross-encoders are general-purpose; don't know financial tables are critical

### Table Preference for Financial Documents

For queries like "What were the revenue numbers?":
- **Query type**: `data_query`
- **Hybrid retrieval**: Tables boosted 20%, narrative penalized 10%
- **Re-ranker**: Tables boosted 10%, narrative penalized 5%
- **Result**: Tables consistently ranked higher throughout pipeline

## Monitoring & Debugging

### Chunk Metadata

Each chunk now includes:
```python
{
    "text": "...",
    "hybrid_score": 0.85,           # After hybrid retrieval
    "rerank_score": 0.92,           # After re-ranking
    "metadata_boost": 1.1,          # Boost factor applied
    "compression_applied": True,    # Whether compressed
    "compression_method": "llmlingua",  # "llmlingua", "truncate", "llmlingua+truncate"
    "original_tokens": 750,         # Before compression
    "compressed_tokens": 480,       # After compression
    "compression_ratio": 0.64       # 64% of original size
}
```

### Logging

Check logs for:
- `Hybrid retrieval complete: 20 candidates retrieved`
- `Re-ranking complete: 10 final chunks selected`
- `Applied metadata boosting to rerank scores`
- `Compressed chunk: 750 → 480 tokens (llmlingua)`

## Performance Considerations

### Latency
- **Hybrid retrieval**: ~50-100ms
- **Re-ranking (10 chunks)**: ~100-200ms
- **Total overhead**: ~150-300ms

### Trade-offs
- **Quality**: Re-ranking significantly improves relevance
- **Speed**: Adds ~200ms latency (acceptable for chat)
- **Cost**: No additional API costs (local models)

## Future Improvements

1. **Caching**: Cache cross-encoder scores for repeated queries
2. **Batch re-ranking**: Re-rank multiple queries in parallel
3. **Model fine-tuning**: Fine-tune cross-encoder on financial documents
4. **Adaptive compression**: Dynamic compression rate based on chunk importance
5. **Hybrid compression**: Combine LLMLingua with extractive summarization

## Troubleshooting

### Re-ranker not loading
```bash
# Ensure sentence-transformers is installed
pip install sentence-transformers==3.3.1

# Test cross-encoder loading
python -c "from sentence_transformers import CrossEncoder; CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"
```

### LLMLingua not working
```bash
# Install llmlingua
pip install llmlingua==0.2.2

# Test import
python -c "from llmlingua import PromptCompressor; PromptCompressor()"
```

### Compression too aggressive
```python
# Increase compression rate (less compression)
rag_compression_rate=0.7  # 70% of original (default: 0.5)
```

### Re-ranking too slow
```python
# Use smaller batch size
rag_reranker_batch_size=4  # (default: 8)

# Or use faster model
rag_reranker_model="cross-encoder/ms-marco-MiniLM-L-6-v2"  # Fastest
```

## References

- [LLMLingua Paper](https://arxiv.org/abs/2310.05736)
- [LLMLingua-2 Paper](https://arxiv.org/abs/2403.12968)
- [MS MARCO Cross-Encoders](https://www.sbert.net/docs/pretrained_cross-encoders.html)
- [BGE Reranker](https://huggingface.co/BAAI/bge-reranker-base)
