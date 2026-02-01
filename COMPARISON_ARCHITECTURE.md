# Document Comparison Architecture

## System Components

```
┌─────────────────────────────────────────────────────────────────────────┐
│                            RAG SERVICE                                   │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │ chat() - Main Entry Point                                          │ │
│  │                                                                     │ │
│  │  1. Load conversation history                                      │ │
│  │  2. Query Analyzer → is_comparison?                                │ │
│  │                                                                     │ │
│  │  ┌──────────────────────┐       ┌─────────────────────────────┐   │ │
│  │  │  Standard Flow       │       │  Comparison Flow (NEW)      │   │ │
│  │  │  (is_comparison=False)│       │  (is_comparison=True)       │   │ │
│  │  └──────────────────────┘       └─────────────────────────────┘   │ │
│  │           │                                    │                    │ │
│  │           ↓                                    ↓                    │ │
│  │  ┌──────────────────┐           ┌──────────────────────────────┐   │ │
│  │  │ Hybrid Retriever │           │ Document Filter (NEW)        │   │ │
│  │  │ All documents    │           │ - Extract doc names          │   │ │
│  │  │ mixed together   │           │ - Fuzzy match filenames      │   │ │
│  │  └────────┬─────────┘           │ - Filter to specific docs    │   │ │
│  │           │                     └──────────────┬───────────────┘   │ │
│  │           ↓                                    ↓                    │ │
│  │  ┌──────────────────┐           ┌──────────────────────────────┐   │ │
│  │  │ Standard Prompt  │           │ Check Count & Warn           │   │ │
│  │  │ Builder          │           │ if >3 documents              │   │ │
│  │  └────────┬─────────┘           └──────────────┬───────────────┘   │ │
│  │           │                                     ↓                   │ │
│  │           │                     ┌──────────────────────────────┐   │ │
│  │           │                     │ _chat_comparison()           │   │ │
│  │           │                     │ (orchestration)              │   │ │
│  │           │                     └──────────────┬───────────────┘   │ │
│  │           │                                    │                    │ │
│  │           │                                    ↓                    │ │
│  │           │                     ┌──────────────────────────────┐   │ │
│  │           │                     │ ComparisonRetriever (NEW)    │   │ │
│  │           │                     │ - Per-doc retrieval          │   │ │
│  │           │                     │ - Pairing/Clustering         │   │ │
│  │           │                     └──────────────┬───────────────┘   │ │
│  │           │                                    │                    │ │
│  │           │                                    ↓                    │ │
│  │           │                     ┌──────────────────────────────┐   │ │
│  │           │                     │ Comparison Prompt Builder    │   │ │
│  │           │                     │ - Side-by-side content       │   │ │
│  │           │                     │ - Table format instructions  │   │ │
│  │           │                     └──────────────┬───────────────┘   │ │
│  │           │                                    │                    │ │
│  │           └────────────────┬───────────────────┘                    │ │
│  │                            ↓                                        │ │
│  │                  ┌──────────────────┐                               │ │
│  │                  │  LLM Streaming   │                               │ │
│  │                  │  (Claude Sonnet) │                               │ │
│  │                  └────────┬─────────┘                               │ │
│  │                           │                                         │ │
│  │                           ↓                                         │ │
│  │            ┌──────────────────────────────┐                         │ │
│  │            │ Response:                    │                         │ │
│  │            │ - Generic answer OR          │                         │ │
│  │            │ - Comparison table + analysis│                         │ │
│  │            └──────────────────────────────┘                         │ │
│  └─────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

## Per-Document Retrieval Pipeline (Comparison Mode)

```
For each document in filtered list:

┌──────────────────────────────────────────────────────────────┐
│ Document ID                                                   │
└────────────────────────────┬─────────────────────────────────┘
                             ↓
┌──────────────────────────────────────────────────────────────┐
│ STEP 1: Hybrid Retrieval                                     │
│ ┌──────────────────┐    ┌──────────────────┐                │
│ │ Semantic Search  │    │ Keyword Search   │                │
│ │ (pgvector HNSW)  │    │ (PostgreSQL FTS) │                │
│ │ Top 20           │    │ Top 20           │                │
│ └────────┬─────────┘    └────────┬─────────┘                │
│          │                       │                           │
│          └───────────┬───────────┘                           │
│                      ↓                                       │
│          ┌───────────────────────┐                           │
│          │ RRF Fusion            │                           │
│          │ (Reciprocal Rank)     │                           │
│          │ → 20 candidates       │                           │
│          └───────────┬───────────┘                           │
└──────────────────────┼───────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────────────────┐
│ STEP 2: Query Analysis + Metadata Boosting                   │
│                                                               │
│ Query Analyzer:                                               │
│ - Detects table/narrative preference                          │
│ - table_boost=1.2 or narrative_boost=1.1                     │
│                                                               │
│ Metadata Booster:                                             │
│ - Boosts scores based on chunk_type (table vs narrative)     │
│ - Adaptive to query intent                                    │
│ → 20 boosted candidates                                       │
└──────────────────────┼───────────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────────────────┐
│ STEP 3: Re-ranking with Cross-Encoder                        │
│                                                               │
│ Model: cross-encoder/ms-marco-MiniLM-L-6-v2                  │
│ - Computes query-chunk relevance scores                      │
│ - Much more accurate than embeddings                          │
│ - Sort by rerank_score                                        │
│ → Top 10 chunks                                               │
└──────────────────────┼───────────────────────────────────────┘
                       ↓
                 Final chunks for this document
```

## Pairing/Clustering Algorithm

### 2-Document Pairwise Matching

```
Document A chunks (10)    Document B chunks (10)
      ┌───────┐                ┌───────┐
      │ Chunk │                │ Chunk │
      │  A1   │◄───0.85───────►│  B3   │  ← Paired (high similarity)
      └───────┘                └───────┘
      ┌───────┐                ┌───────┐
      │ Chunk │                │ Chunk │
      │  A2   │◄───0.72───────►│  B5   │  ← Paired
      └───────┘                └───────┘
      ┌───────┐                ┌───────┐
      │ Chunk │     0.45       │ Chunk │
      │  A3   │ ─ ─ ─ ─ ─ ─ ─ ─│  B2   │  ← Not paired (below threshold)
      └───────┘                └───────┘

Algorithm:
1. For each chunk in Doc A:
   - Find best matching chunk in Doc B (highest similarity)
   - If similarity >= 0.6, create pair
   - Mark Doc B chunk as used
2. Sort pairs by similarity (descending)
3. Take top 8 pairs for prompt
```

### 3-Document Greedy Clustering

```
Doc A (anchor)      Doc B             Doc C
  ┌───────┐
  │ Chunk │───0.78──►┌───────┐
  │  A1   │          │ Chunk │
  │       │          │  B2   │
  └───┬───┘          └───────┘
      │
      └──────0.82──────►┌───────┐
                        │ Chunk │
                        │  C5   │
                        └───────┘
         ↑
         └─────────────── Cluster 1 (all 3 docs)

  ┌───────┐
  │ Chunk │───0.91──►┌───────┐
  │  A2   │          │ Chunk │
  │       │          │  B7   │
  └───────┘          └───────┘

                     (No match in C above 0.6)

         ↑
         └─────────────── Cluster 2 (only A+B)

Algorithm:
1. Use first document as anchor
2. For each anchor chunk:
   - Find best match in Doc B (if >= 0.6)
   - Find best match in Doc C (if >= 0.6)
   - Create cluster if ≥2 docs have matches
3. Mark chunks as used to avoid duplicates
4. Take top 8 clusters for prompt
```

## Document Filtering Flow

```
User Query: "Compare Property A with Property B"
                    ↓
┌──────────────────────────────────────────────────────────┐
│ Step 1: Extract Document Names                          │
│                                                          │
│ Regex patterns:                                          │
│ - "compare X and Y" → ["Property A", "Property B"]      │
│ - "X vs Y"          → ["X", "Y"]                        │
│ - "between X and Y" → ["X", "Y"]                        │
│                                                          │
│ Extracted: ["Property A", "Property B"]                 │
└──────────────────────┬───────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────────────┐
│ Step 2: Load Document Filenames from Session            │
│                                                          │
│ Session documents:                                        │
│ - doc_id_1 → "Property_A_Offering_Memo.pdf"             │
│ - doc_id_2 → "Property_B_Final_OM.pdf"                  │
│ - doc_id_3 → "Property_C_Presentation.pdf"              │
│ - doc_id_4 → "Background_Research.pdf"                  │
└──────────────────────┬───────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────────────┐
│ Step 3: Fuzzy Match                                      │
│                                                          │
│ For "Property A":                                        │
│ - vs "Property_A_Offering_Memo.pdf" → 0.85 ✓           │
│ - vs "Property_B_Final_OM.pdf"      → 0.45             │
│ - vs "Property_C_Presentation.pdf"  → 0.40             │
│ - vs "Background_Research.pdf"      → 0.20             │
│ → Best match: doc_id_1 (Property_A)                     │
│                                                          │
│ For "Property B":                                        │
│ - vs "Property_A_Offering_Memo.pdf" → 0.45             │
│ - vs "Property_B_Final_OM.pdf"      → 0.87 ✓           │
│ - vs "Property_C_Presentation.pdf"  → 0.41             │
│ - vs "Background_Research.pdf"      → 0.22             │
│ → Best match: doc_id_2 (Property_B)                     │
└──────────────────────┬───────────────────────────────────┘
                       ↓
┌──────────────────────────────────────────────────────────┐
│ Step 4: Filter                                           │
│                                                          │
│ Original: [doc_id_1, doc_id_2, doc_id_3, doc_id_4]      │
│ Filtered: [doc_id_1, doc_id_2]                          │
│                                                          │
│ → Compare only Property A and Property B                 │
└──────────────────────────────────────────────────────────┘
```

## Comparison Output Format

### 2-Document Comparison

```markdown
## Documents Being Compared
**Document A:** Property_A_Offering_Memo.pdf
**Document B:** Property_B_Final_OM.pdf

## Paired Content (Related Sections)

### Comparison Point 1: Financial Performance
**From Property_A_Offering_Memo.pdf (Page 5) [DocA:p5]:**
The property generated $1.2M in NOI for 2024, reflecting a 6.2% cap rate
on the $19.4M purchase price...

**From Property_B_Final_OM.pdf (Page 3) [DocB:p3]:**
Net operating income of $1.1M translates to a 5.8% capitalization rate
based on the $19.0M acquisition cost...

### Comparison Point 2: Occupancy
...

================================================================================
USER QUESTION: Compare the cap rates and NOI
================================================================================

Generate your comparison with:
1. A markdown comparison table (3-8 rows) with Difference column
2. 2-3 paragraphs analyzing the key differences
3. Clear recommendation or conclusion

Every claim must have a citation [DocA:pN] or [DocB:pN].

ANSWER:
```

### LLM Response Example

```markdown
| Metric | Property A | Property B | Difference |
|--------|------------|------------|------------|
| Cap Rate | 6.2% [DocA:p5] | 5.8% [DocB:p3] | +0.4% |
| NOI | $1.2M [DocA:p5] | $1.1M [DocB:p3] | +$100K |
| Purchase Price | $19.4M [DocA:p5] | $19.0M [DocB:p3] | +$400K |

Property A demonstrates stronger financial performance with a higher
capitalization rate of 6.2% compared to Property B's 5.8% [DocA:p5, DocB:p3].
The $100K difference in NOI ($1.2M vs $1.1M) contributes to this spread,
despite Property A having a slightly higher purchase price.

The 0.4% cap rate difference represents a meaningful advantage for Property A,
suggesting better income generation relative to acquisition cost. This could
indicate either stronger operational performance or more favorable purchase
terms.

**Recommendation:** Property A offers superior current yield and may represent
the better investment from a cash flow perspective, though other factors like
location, asset quality, and growth potential should be considered.
```

## Key Design Decisions

1. **Why cross-encoder for pairing instead of Jaccard/cosine similarity?**
   - Cross-encoder provides much more accurate semantic similarity than word overlap
   - Reuses existing cross-encoder model already in the pipeline (no extra dependencies)
   - Batch processing keeps it efficient (10x10 = 100 comparisons per 2-doc pair)
   - Normalized scores (sigmoid) ensure consistent 0-1 range for threshold matching
   - Fallback to Jaccard similarity if cross-encoder fails

2. **Why limit to 3 documents?**
   - Prompt size management (3 docs × 10 chunks × 8 pairs = ~240 chunks max)
   - Table readability (4+ columns get hard to parse)
   - LLM quality degrades with too many docs to compare
   - User can specify which docs to compare if they have more

3. **Why separate pipelines per document?**
   - Ensures balanced representation (10 chunks from each)
   - Standard retrieval would favor one document over others
   - Maintains full quality of hybrid + rerank per doc

4. **Why greedy clustering instead of k-means?**
   - Don't know number of clusters in advance
   - Greedy is simple and deterministic
   - Respects original ranking (anchors on first doc's top chunks)
   - Good enough for 3 documents

5. **Why fuzzy matching instead of exact matching?**
   - Users won't type exact filenames
   - Handles variations ("Property A" vs "Property_A_OM.pdf")
   - Robust to typos and abbreviations
   - Substring boost handles partial names
