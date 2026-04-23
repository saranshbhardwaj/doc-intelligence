# RE Underwriting Extraction Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the RE underwriting extraction pipeline to fix a broken Celery chain, eliminate large Redis payloads, add two-tier extraction (direct vs. map-reduce) with proper per-doc Pydantic schemas, and apply CRE-standard merge priority rules.

**Architecture:** Each document (OM, T-12, Rent Roll) is extracted independently in parallel via `chord(group(...), chain(...))`. Per-doc tasks fetch their own chunks from DB (IDs only through Redis). Docs under 80K chars go through a single LLM call; larger docs use Phase 1 (batch condensation) + Phase 2 (schema fitting). The merge task applies CRE priority rules (T-12 actuals > OM projections for operating figures, Rent Roll > OM for unit counts), then discrepancy detection flags cross-doc conflicts > 10%.

**Tech Stack:** Python, Celery (`chord`, `group`, `chain`), Pydantic v2, Anthropic Haiku 4.5, SQLAlchemy, FastAPI, pytest

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `backend/app/config.py` | 5 new RE underwriting config values |
| Modify | `backend/app/verticals/real_estate/underwriting/schemas/self_storage.py` | Add `lease_records` to `SelfStorageInputs` |
| **Create** | `backend/app/verticals/real_estate/underwriting/extraction/schemas.py` | `OMExtraction`, `T12Extraction`, `RentRollExtraction`, `CondensedBatchExtraction`, `ExtractedDocResult` |
| Modify | `backend/app/verticals/real_estate/underwriting/extraction/prompts.py` | Add Phase 1 condensation prompt + Phase 2 schema-fitting prompts per doc type |
| Modify | `backend/app/verticals/real_estate/underwriting/extraction/llm_service.py` | Add `condense_batch()` and `reduce_to_schema()` methods |
| **Create** | `backend/app/verticals/real_estate/underwriting/extraction/extractor.py` | `batch_chunks_by_chars()`, `build_chunk_context()`, `extract_document()` — two-tier dispatch |
| **Create** | `backend/app/verticals/real_estate/underwriting/extraction/merger.py` | `merge_extractions()` — CRE priority rules, annualise T-6, produce `SelfStorageInputs` dict |
| Modify | `backend/app/verticals/real_estate/underwriting/extraction/discrepancy.py` | Update to accept typed `ExtractedDocResult` list |
| Modify | `backend/app/verticals/real_estate/underwriting/extraction/tasks/tasks.py` | Fix `chord`/`group`, ID-only payloads, `soft_time_limit`, `acks_late`, `reject_on_worker_lost` |
| Modify | `backend/app/verticals/real_estate/api/underwriting.py` | Remove chunk fetching — pass `document_id` + `doc_type` only to Celery |
| Modify | `backend/app/core/lifespan.py` | Add stale underwriting run sweep to `periodic_cleanup()` |
| **Create** | `backend/tests/unit/verticals/real_estate/underwriting/__init__.py` | Empty |
| **Create** | `backend/tests/unit/verticals/real_estate/underwriting/test_extractor.py` | Unit tests for batching + context building |
| **Create** | `backend/tests/unit/verticals/real_estate/underwriting/test_merger.py` | Unit tests for CRE merge priority rules |

---

## Task 1: Add Config Values

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: Find the RE-related config section**

Open `backend/app/config.py`. Search for `max_pages_per_extraction` — the new values go after it.

- [ ] **Step 2: Add the five config values**

```python
# RE Underwriting extraction
re_uw_full_text_max_chars: int = 80_000         # below → direct single LLM call per doc
re_uw_map_reduce_max_chars_per_batch: int = 20_000  # hard char cap per Phase 1 batch
re_uw_discrepancy_threshold_pct: float = 0.10   # flag if sources differ by > 10%
re_uw_task_soft_time_limit_seconds: int = 600   # 10 min → SoftTimeLimitExceeded → mark_error
re_uw_stale_job_timeout_minutes: int = 20       # periodic_cleanup sweeps runs stuck here
```

- [ ] **Step 3: Verify the app still loads**

```bash
cd backend && python -c "from app.config import settings; print(settings.re_uw_full_text_max_chars)"
```
Expected output: `80000`

---

## Task 2: Add `lease_records` to `SelfStorageInputs`

**Files:**
- Modify: `backend/app/verticals/real_estate/underwriting/schemas/self_storage.py`

The existing `re_calculate_underwriting_task` references `inputs.lease_records` but the schema doesn't have it. This is a latent bug.

- [ ] **Step 1: Add import and field**

In `self_storage.py`, add `lease_records` to `SelfStorageInputs`:

```python
class SelfStorageInputs(BaseModel):
    """Complete wizard inputs — one instance per underwriting run."""

    model_config = ConfigDict(populate_by_name=True)

    project: ProjectDetails
    acquisition: AcquisitionInputs
    operational: OperationalInputs
    financing: FinancingInputs
    exit: ExitInputs
    criteria: InvestmentCriteria
    lease_records: list[LeaseRecord] = Field(
        default_factory=list,
        description="Lease records from rent roll — used for rollover risk.",
    )
```

- [ ] **Step 2: Verify schema round-trips**

```bash
cd backend && python -c "
from app.verticals.real_estate.underwriting.schemas.self_storage import SelfStorageInputs
import json
raw = {'project': {'name': 'Test'}, 'acquisition': {'purchase_price': 1000000}, 'operational': {'gross_potential_rent_annual': 100000}, 'financing': {}, 'exit': {}, 'criteria': {}}
s = SelfStorageInputs(**raw)
print('lease_records:', s.lease_records)
"
```
Expected: `lease_records: []`

---

## Task 3: Create Per-Doc Extraction Schemas

**Files:**
- Create: `backend/app/verticals/real_estate/underwriting/extraction/schemas.py`
- Test: `backend/tests/unit/verticals/real_estate/underwriting/test_extractor.py` (started here)

- [ ] **Step 1: Create the schemas file**

```python
"""Per-document extraction schemas for RE underwriting.

Each doc type gets its own typed schema. All fields Optional — a doc may
not contain every field. The merger maps these into SelfStorageInputs.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field

from ..schemas.self_storage import LeaseRecord


class OMExtraction(BaseModel):
    """Structured data extracted from an Offering Memorandum."""

    name: Optional[str] = None
    address: Optional[str] = None
    purchase_price: Optional[float] = None
    closing_cost_pct: Optional[float] = None
    capex_reserve_per_unit: Optional[float] = None
    num_units: Optional[int] = None
    rentable_sqft: Optional[float] = None
    year_built: Optional[int] = None
    gpr_annual_projected: Optional[float] = None
    vacancy_pct_projected: Optional[float] = None
    noi_projected: Optional[float] = None
    mgmt_fee_pct: Optional[float] = None
    exit_cap_rate: Optional[float] = None
    hold_period_years: Optional[int] = None
    selling_cost_pct: Optional[float] = None
    target_irr: Optional[float] = None
    target_cash_on_cash: Optional[float] = None
    target_equity_multiple: Optional[float] = None
    ltv_pct: Optional[float] = None
    interest_rate_pct: Optional[float] = None
    amortization_years: Optional[int] = None
    loan_term_years: Optional[int] = None


class T12Extraction(BaseModel):
    """Structured data extracted from a T-12 or T-6 operating statement."""

    gpr_annual_actual: Optional[float] = None
    vacancy_credit_loss_pct_actual: Optional[float] = None
    other_income_annual: Optional[float] = None
    property_tax_annual: Optional[float] = None
    insurance_annual: Optional[float] = None
    mgmt_fee_pct_actual: Optional[float] = None
    payroll_annual: Optional[float] = None
    repairs_maintenance_annual: Optional[float] = None
    utilities_annual: Optional[float] = None
    marketing_annual: Optional[float] = None
    other_opex_annual: Optional[float] = None
    noi_actual: Optional[float] = None
    period_months: Optional[int] = None  # 12 or 6 — used to annualise T-6 (× 12/period_months)


class RentRollExtraction(BaseModel):
    """Structured data extracted from a Rent Roll."""

    num_units_actual: Optional[int] = None
    physical_occupancy_pct: Optional[float] = None
    lease_records: list[LeaseRecord] = Field(default_factory=list)
    rent_growth_pct: Optional[float] = None


class CondensedField(BaseModel):
    """One financially relevant data point from a Phase 1 condensation batch."""

    field: str
    value: str
    citations: list[str] = Field(default_factory=list)
    source_text: str = ""


class CondensedBatchExtraction(BaseModel):
    """Output of one Phase 1 (map) LLM call over a batch of chunks."""

    fields: list[CondensedField] = Field(default_factory=list)


class ExtractedDocResult(BaseModel):
    """Result of extracting one document. Passed (as small JSON) to merge task."""

    run_id: str
    job_id: str
    doc_type: str  # "om" | "t12" | "rent_roll"
    om: Optional[OMExtraction] = None
    t12: Optional[T12Extraction] = None
    rent_roll: Optional[RentRollExtraction] = None
    field_citations: dict = Field(default_factory=dict)
    error: Optional[str] = None  # set if optional doc extraction failed
```

- [ ] **Step 2: Create test init file**

```bash
mkdir -p backend/tests/unit/verticals/real_estate/underwriting
touch backend/tests/unit/verticals/real_estate/underwriting/__init__.py
touch backend/tests/integration/verticals/real_estate/underwriting/__init__.py
```

- [ ] **Step 3: Write a smoke test**

Create `backend/tests/unit/verticals/real_estate/underwriting/test_extractor.py`:

```python
"""Unit tests for RE underwriting extraction utilities."""
import pytest
from app.verticals.real_estate.underwriting.extraction.schemas import (
    OMExtraction,
    T12Extraction,
    RentRollExtraction,
    ExtractedDocResult,
)


def test_om_extraction_all_optional():
    om = OMExtraction()
    assert om.purchase_price is None
    assert om.num_units is None


def test_t12_extraction_period_months():
    t12 = T12Extraction(gpr_annual_actual=480000.0, period_months=6)
    assert t12.period_months == 6
    assert t12.gpr_annual_actual == 480000.0


def test_extracted_doc_result_error_field():
    result = ExtractedDocResult(run_id="r1", job_id="j1", doc_type="t12", error="timeout")
    assert result.error == "timeout"
    assert result.t12 is None
```

- [ ] **Step 4: Run the smoke test**

```bash
cd backend && python -m pytest tests/unit/verticals/real_estate/underwriting/test_extractor.py -v
```
Expected: 3 passed.

---

## Task 4: Add Phase 1 + Phase 2 Prompts

**Files:**
- Modify: `backend/app/verticals/real_estate/underwriting/extraction/prompts.py`

- [ ] **Step 1: Append Phase 1 condensation prompt to `prompts.py`**

Add after the existing `create_t12_user_prompt` function:

```python
# ── Phase 1: Schema-agnostic condensation (map step) ─────────────────────────

PHASE1_CONDENSATION_SYSTEM_PROMPT = """You are extracting financially relevant data from real estate document chunks.

Extract every financial figure, property metric, and deal term you find.
Return raw values only — no calculations, no inference.

CHUNK TYPES (indicated in each chunk header):
- KV Pair: Highest confidence — data is already structured. Extract exactly as shown.
- Table Chunk: High confidence — extract every numeric column and row.
- Narrative: Extract only explicitly stated figures (e.g. "$485,000 annual rent"). Skip vague descriptions.

CITATION: Each chunk starts with a token like [S1:p5]. Use that exact token in citations.

NUMBERS: Remove $, commas. Convert percentages to decimals. "$1,234,567" → "1234567". "95%" → "0.95".

Return ONLY valid JSON, no markdown:
{
  "fields": [
    {
      "field": "descriptive_field_name",
      "value": "numeric_or_text_value",
      "citations": ["[S1:p5]"],
      "source_text": "brief snippet"
    }
  ]
}"""


def create_phase1_user_prompt(chunk_context: str) -> str:
    return f"""Extract all financially relevant data from these document chunks:

{chunk_context}

Return JSON only."""


# ── Phase 2: Schema-fitting (reduce step) per doc type ───────────────────────

import json as _json


def _schema_json(fields: list[dict]) -> str:
    return _json.dumps({f["name"]: f.get("type", "float | null") for f in fields}, indent=2)


_OM_FIELDS = [
    {"name": "name", "type": "str | null"},
    {"name": "address", "type": "str | null"},
    {"name": "purchase_price", "type": "float | null"},
    {"name": "closing_cost_pct", "type": "float | null (decimal, e.g. 0.02)"},
    {"name": "capex_reserve_per_unit", "type": "float | null"},
    {"name": "num_units", "type": "int | null"},
    {"name": "rentable_sqft", "type": "float | null"},
    {"name": "year_built", "type": "int | null"},
    {"name": "gpr_annual_projected", "type": "float | null (annual)"},
    {"name": "vacancy_pct_projected", "type": "float | null (decimal, e.g. 0.08)"},
    {"name": "noi_projected", "type": "float | null (annual)"},
    {"name": "mgmt_fee_pct", "type": "float | null (decimal)"},
    {"name": "exit_cap_rate", "type": "float | null (decimal, e.g. 0.065)"},
    {"name": "hold_period_years", "type": "int | null"},
    {"name": "selling_cost_pct", "type": "float | null (decimal)"},
    {"name": "target_irr", "type": "float | null (decimal)"},
    {"name": "target_cash_on_cash", "type": "float | null (decimal)"},
    {"name": "target_equity_multiple", "type": "float | null"},
    {"name": "ltv_pct", "type": "float | null (decimal, e.g. 0.70)"},
    {"name": "interest_rate_pct", "type": "float | null (decimal, e.g. 0.065)"},
    {"name": "amortization_years", "type": "int | null"},
    {"name": "loan_term_years", "type": "int | null"},
]

_T12_FIELDS = [
    {"name": "gpr_annual_actual", "type": "float | null (annualised if T-6)"},
    {"name": "vacancy_credit_loss_pct_actual", "type": "float | null (decimal)"},
    {"name": "other_income_annual", "type": "float | null"},
    {"name": "property_tax_annual", "type": "float | null"},
    {"name": "insurance_annual", "type": "float | null"},
    {"name": "mgmt_fee_pct_actual", "type": "float | null (decimal)"},
    {"name": "payroll_annual", "type": "float | null"},
    {"name": "repairs_maintenance_annual", "type": "float | null"},
    {"name": "utilities_annual", "type": "float | null"},
    {"name": "marketing_annual", "type": "float | null"},
    {"name": "other_opex_annual", "type": "float | null"},
    {"name": "noi_actual", "type": "float | null"},
    {"name": "period_months", "type": "int | null (12 or 6)"},
]

_RENT_ROLL_FIELDS = [
    {"name": "num_units_actual", "type": "int | null"},
    {"name": "physical_occupancy_pct", "type": "float | null (decimal)"},
    {"name": "rent_growth_pct", "type": "float | null (decimal, if stated)"},
    {"name": "lease_records", "type": "array of {unit_id, monthly_rent, lease_expiration (YYYY-MM-DD), sqft}"},
]


def _phase2_system(doc_label: str, fields: list[dict], condensed_json: str) -> str:
    return f"""You are converting condensed field extractions into a typed {doc_label} underwriting schema.

The condensed data below was extracted from a real estate document.
Map field values to the schema. Rules:
- Monetary values: float, no symbols or commas
- Percentages: decimal (0.065 not 6.5%)
- "purchase price", "asking price", "listing price" → purchase_price
- "gross potential rent", "GPR", "scheduled rent" → gpr_annual_projected (annualised)
- "exit cap", "going-out cap", "terminal cap" → exit_cap_rate
- "hold period", "investment horizon" → hold_period_years
- If a value genuinely cannot be found, return null

Condensed data:
{condensed_json}

Return ONLY valid JSON matching this schema (null for missing):
{_schema_json(fields)}"""


def create_phase2_om_prompt(condensed_json: str) -> str:
    return _phase2_system("Offering Memorandum (OM)", _OM_FIELDS, condensed_json)


def create_phase2_t12_prompt(condensed_json: str) -> str:
    return _phase2_system("T-12/T-6 Operating Statement", _T12_FIELDS, condensed_json)


def create_phase2_rent_roll_prompt(condensed_json: str) -> str:
    return _phase2_system("Rent Roll", _RENT_ROLL_FIELDS, condensed_json)
```

- [ ] **Step 2: Verify import**

```bash
cd backend && python -c "
from app.verticals.real_estate.underwriting.extraction.prompts import (
    PHASE1_CONDENSATION_SYSTEM_PROMPT,
    create_phase1_user_prompt,
    create_phase2_om_prompt,
)
print('OK', len(PHASE1_CONDENSATION_SYSTEM_PROMPT))
"
```
Expected: `OK` followed by a number > 100.

---

## Task 5: Add Map-Reduce Methods to LLM Service

**Files:**
- Modify: `backend/app/verticals/real_estate/underwriting/extraction/llm_service.py`

- [ ] **Step 1: Add imports at the top of `llm_service.py`**

Add after existing imports:

```python
import json as _json
from .schemas import OMExtraction, T12Extraction, RentRollExtraction, CondensedBatchExtraction
from .prompts import (
    PHASE1_CONDENSATION_SYSTEM_PROMPT,
    create_phase1_user_prompt,
    create_phase2_om_prompt,
    create_phase2_t12_prompt,
    create_phase2_rent_roll_prompt,
)
```

- [ ] **Step 2: Add `condense_batch()` method to `REExtractionLLMService`**

```python
def condense_batch(self, chunk_context: str) -> CondensedBatchExtraction:
    """Phase 1 (map): extract all financially relevant data from a chunk batch."""
    try:
        message = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            temperature=0,
            system=[{
                "type": "text",
                "text": PHASE1_CONDENSATION_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }],
            messages=[{"role": "user", "content": create_phase1_user_prompt(chunk_context)}],
        )
        text = message.content[0].text.strip()
        data = self._parse_json(text, "phase1_condensation")
        return CondensedBatchExtraction(**data) if data else CondensedBatchExtraction()
    except Exception as e:
        logger.error(f"Phase 1 condensation failed: {e}")
        return CondensedBatchExtraction()
```

- [ ] **Step 3: Add `reduce_to_schema()` method to `REExtractionLLMService`**

```python
def reduce_to_schema(self, doc_type: str, condensed_fields: list[dict]) -> dict:
    """Phase 2 (reduce): fit condensed fields into the typed per-doc schema."""
    condensed_json = _json.dumps(condensed_fields, indent=2)
    if doc_type == "om":
        prompt = create_phase2_om_prompt(condensed_json)
        model_cls = OMExtraction
    elif doc_type == "t12":
        prompt = create_phase2_t12_prompt(condensed_json)
        model_cls = T12Extraction
    else:
        prompt = create_phase2_rent_roll_prompt(condensed_json)
        model_cls = RentRollExtraction
    try:
        message = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            temperature=0,
            system=[],
            messages=[{"role": "user", "content": prompt}],
        )
        text = message.content[0].text.strip()
        data = self._parse_json(text, f"phase2_{doc_type}")
        return data or {}
    except Exception as e:
        logger.error(f"Phase 2 reduce failed for {doc_type}: {e}")
        return {}
```

- [ ] **Step 4: Verify the class still imports cleanly**

```bash
cd backend && python -c "
from app.services.llm_client import LLMClient
from app.verticals.real_estate.underwriting.extraction.llm_service import REExtractionLLMService
print('OK — methods:', [m for m in dir(REExtractionLLMService) if not m.startswith('_')])
"
```
Expected: list includes `condense_batch` and `reduce_to_schema`.

---

## Task 6: Create Extractor Module

**Files:**
- Create: `backend/app/verticals/real_estate/underwriting/extraction/extractor.py`
- Test: `backend/tests/unit/verticals/real_estate/underwriting/test_extractor.py`

- [ ] **Step 1: Write the failing tests first**

Add to `backend/tests/unit/verticals/real_estate/underwriting/test_extractor.py`:

```python
from unittest.mock import MagicMock
from app.verticals.real_estate.underwriting.extraction.extractor import (
    batch_chunks_by_chars,
    build_chunk_context,
)


# ── batch_chunks_by_chars ────────────────────────────────────────────────────

def _make_chunk(content: str, page: int = 1, is_tabular: bool = False, section_type: str = "narrative"):
    c = MagicMock()
    c.content = content
    c.page_number = page
    c.is_tabular = is_tabular
    c.section_type = section_type
    c.chunk_metadata = {"bbox": {"page": page}}
    return c


def test_batch_chunks_single_batch():
    chunks = [_make_chunk("a" * 1000) for _ in range(5)]
    batches = batch_chunks_by_chars(chunks, max_chars=10_000)
    assert len(batches) == 1
    assert sum(len(c.content) for c in batches[0]) == 5000


def test_batch_chunks_splits_on_budget():
    chunks = [_make_chunk("a" * 8000) for _ in range(3)]
    batches = batch_chunks_by_chars(chunks, max_chars=10_000)
    assert len(batches) == 3  # each 8K chunk starts a new batch


def test_batch_chunks_empty_input():
    assert batch_chunks_by_chars([], max_chars=20_000) == []


def test_batch_chunks_single_oversized_chunk_goes_alone():
    chunks = [_make_chunk("a" * 25_000)]
    batches = batch_chunks_by_chars(chunks, max_chars=20_000)
    assert len(batches) == 1  # oversized but nowhere else to go


# ── build_chunk_context ──────────────────────────────────────────────────────

def test_build_chunk_context_includes_citation():
    chunk = _make_chunk("GPR: $485,000", page=5)
    ctx = build_chunk_context([chunk], source_index=1)
    assert "[S1:p5]" in ctx
    assert "GPR: $485,000" in ctx


def test_build_chunk_context_labels_table():
    chunk = _make_chunk("Unit | Rent", page=3, is_tabular=True)
    ctx = build_chunk_context([chunk], source_index=2)
    assert "[S2:p3]" in ctx
    assert "Table Chunk" in ctx


def test_build_chunk_context_labels_kv():
    chunk = _make_chunk("Price: $1.2M", page=1, section_type="key_value")
    ctx = build_chunk_context([chunk], source_index=1)
    assert "KV Pair" in ctx
```

- [ ] **Step 2: Run to confirm failures**

```bash
cd backend && python -m pytest tests/unit/verticals/real_estate/underwriting/test_extractor.py -v 2>&1 | head -30
```
Expected: ImportError on `extractor` module.

- [ ] **Step 3: Create `extractor.py`**

```python
"""Two-tier document extraction for RE underwriting.

- Direct path: docs <= re_uw_full_text_max_chars → one LLM call
- Map-reduce path: larger docs → Phase 1 batches + Phase 2 reduce
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from app.config import settings
from app.utils.logging import logger

if TYPE_CHECKING:
    from app.db_models_chat import DocumentChunk
    from .llm_service import REExtractionLLMService

from .schemas import (
    CondensedBatchExtraction,
    ExtractedDocResult,
    OMExtraction,
    RentRollExtraction,
    T12Extraction,
)


def batch_chunks_by_chars(
    chunks: list,
    max_chars: int,
) -> list[list]:
    """Split chunks into batches where each batch stays under max_chars.

    An oversized single chunk is placed in its own batch rather than dropped.
    """
    if not chunks:
        return []
    batches: list[list] = []
    current: list = []
    current_chars = 0
    for chunk in chunks:
        n = len(chunk.content)
        if current_chars + n > max_chars and current:
            batches.append(current)
            current, current_chars = [], 0
        current.append(chunk)
        current_chars += n
    if current:
        batches.append(current)
    return batches


def build_chunk_context(chunks: list, source_index: int) -> str:
    """Format chunks as a context string with [SN:pP] citation headers."""
    parts: list[str] = []
    for chunk in chunks:
        page = chunk.page_number or (
            chunk.chunk_metadata.get("bbox", {}).get("page") if chunk.chunk_metadata else None
        ) or "?"
        citation = f"[S{source_index}:p{page}]"

        if chunk.is_tabular:
            chunk_type = "Table Chunk"
        elif getattr(chunk, "section_type", None) == "key_value":
            chunk_type = "KV Pair"
        else:
            chunk_type = "Narrative"

        parts.append(f"{citation} ({chunk_type})\n{chunk.content}")
    return "\n\n".join(parts)


def _parse_extraction(doc_type: str, data: dict):
    """Convert raw LLM dict into the correct typed extraction model."""
    try:
        if doc_type == "om":
            return OMExtraction(**data)
        elif doc_type == "t12":
            return T12Extraction(**data)
        else:
            return RentRollExtraction(**data)
    except Exception as e:
        logger.warning(f"Extraction schema parse failed for {doc_type}: {e}")
        return None


def extract_document(
    run_id: str,
    job_id: str,
    doc_type: str,
    chunks: list,
    service: "REExtractionLLMService",
    source_index: int = 1,
) -> ExtractedDocResult:
    """Extract structured data from one document's chunks.

    Chooses direct or map-reduce path based on total char count.
    source_index: the S-number used in [SN:pP] citation tokens (1-based).
    """
    total_chars = sum(len(c.content) for c in chunks)
    logger.info(
        f"Extracting {doc_type} ({len(chunks)} chunks, {total_chars:,} chars)",
        extra={"run_id": run_id, "doc_type": doc_type},
    )

    if total_chars <= settings.re_uw_full_text_max_chars:
        return _direct_extract(run_id, job_id, doc_type, chunks, service, source_index)
    else:
        return _map_reduce_extract(run_id, job_id, doc_type, chunks, service, source_index)


def _direct_extract(
    run_id: str,
    job_id: str,
    doc_type: str,
    chunks: list,
    service: "REExtractionLLMService",
    source_index: int,
) -> ExtractedDocResult:
    """Single LLM call for docs under the char threshold."""
    context = build_chunk_context(chunks, source_index)
    try:
        if doc_type == "om":
            raw = service.extract_om(context)
        elif doc_type == "t12":
            raw = service.extract_t12(context)
        else:
            raw = service.extract_rent_roll(context)

        typed = _parse_extraction(doc_type, raw)
        field_citations = _build_field_citations(raw, doc_type)
        result = ExtractedDocResult(run_id=run_id, job_id=job_id, doc_type=doc_type, field_citations=field_citations)
        if doc_type == "om":
            result.om = typed
        elif doc_type == "t12":
            result.t12 = typed
        else:
            result.rent_roll = typed
        return result
    except Exception as e:
        logger.error(f"Direct extraction failed for {doc_type}: {e}", extra={"run_id": run_id})
        return ExtractedDocResult(run_id=run_id, job_id=job_id, doc_type=doc_type, error=str(e)[:500])


def _map_reduce_extract(
    run_id: str,
    job_id: str,
    doc_type: str,
    chunks: list,
    service: "REExtractionLLMService",
    source_index: int,
) -> ExtractedDocResult:
    """Phase 1 batch condensation + Phase 2 schema fitting."""
    batches = batch_chunks_by_chars(chunks, settings.re_uw_map_reduce_max_chars_per_batch)
    logger.info(f"Map-reduce: {len(batches)} batches for {doc_type}", extra={"run_id": run_id})

    all_fields: list[dict] = []
    for i, batch in enumerate(batches):
        context = build_chunk_context(batch, source_index)
        condensed: CondensedBatchExtraction = service.condense_batch(context)
        all_fields.extend([f.model_dump() for f in condensed.fields])
        logger.debug(f"Batch {i+1}/{len(batches)}: {len(condensed.fields)} fields condensed")

    raw = service.reduce_to_schema(doc_type, all_fields)
    typed = _parse_extraction(doc_type, raw)
    field_citations = _build_field_citations_from_condensed(all_fields)
    result = ExtractedDocResult(run_id=run_id, job_id=job_id, doc_type=doc_type, field_citations=field_citations)
    if doc_type == "om":
        result.om = typed
    elif doc_type == "t12":
        result.t12 = typed
    else:
        result.rent_roll = typed
    return result


def _build_field_citations(raw: dict, doc_type: str) -> dict:
    """Build field_citations from a direct extraction result dict."""
    citations = {}
    for key, val in raw.items():
        if val is not None and not isinstance(val, (dict, list)):
            citations[f"{doc_type}.{key}"] = []
    return citations


def _build_field_citations_from_condensed(fields: list[dict]) -> dict:
    """Build field_citations from Phase 1 condensed field list."""
    citations: dict = {}
    for f in fields:
        name = f.get("field", "unknown")
        citations[name] = f.get("citations", [])
    return citations
```

- [ ] **Step 4: Run the tests**

```bash
cd backend && python -m pytest tests/unit/verticals/real_estate/underwriting/test_extractor.py -v
```
Expected: all 9 tests pass.

---

## Task 7: Create Merger Module

**Files:**
- Create: `backend/app/verticals/real_estate/underwriting/extraction/merger.py`
- Test: `backend/tests/unit/verticals/real_estate/underwriting/test_merger.py`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/unit/verticals/real_estate/underwriting/test_merger.py`:

```python
"""Unit tests for CRE merge priority rules."""
import pytest
from app.verticals.real_estate.underwriting.extraction.merger import merge_extractions
from app.verticals.real_estate.underwriting.extraction.schemas import (
    ExtractedDocResult,
    OMExtraction,
    T12Extraction,
    RentRollExtraction,
)


def _om_result(run_id="r1", **kwargs) -> ExtractedDocResult:
    return ExtractedDocResult(
        run_id=run_id, job_id="j1", doc_type="om",
        om=OMExtraction(**kwargs)
    )


def _t12_result(run_id="r1", **kwargs) -> ExtractedDocResult:
    return ExtractedDocResult(
        run_id=run_id, job_id="j1", doc_type="t12",
        t12=T12Extraction(**kwargs)
    )


def _rr_result(run_id="r1", **kwargs) -> ExtractedDocResult:
    return ExtractedDocResult(
        run_id=run_id, job_id="j1", doc_type="rent_roll",
        rent_roll=RentRollExtraction(**kwargs)
    )


# ── T-12 wins for operating figures ─────────────────────────────────────────

def test_t12_gpr_beats_om_projection():
    results = [
        _om_result(purchase_price=1_000_000.0, gpr_annual_projected=520_000.0),
        _t12_result(gpr_annual_actual=480_000.0, period_months=12),
    ]
    merged, _ = merge_extractions(results)
    assert merged["operational"]["gross_potential_rent_annual"] == 480_000.0


def test_om_gpr_used_when_no_t12():
    results = [_om_result(purchase_price=1_000_000.0, gpr_annual_projected=520_000.0)]
    merged, _ = merge_extractions(results)
    assert merged["operational"]["gross_potential_rent_annual"] == 520_000.0


# ── T-6 annualisation ────────────────────────────────────────────────────────

def test_t6_gpr_is_annualised():
    results = [
        _om_result(purchase_price=500_000.0),
        _t12_result(gpr_annual_actual=240_000.0, period_months=6),
    ]
    merged, _ = merge_extractions(results)
    # 240_000 * (12/6) = 480_000
    assert merged["operational"]["gross_potential_rent_annual"] == pytest.approx(480_000.0)


# ── OM wins for deal terms ───────────────────────────────────────────────────

def test_om_purchase_price_always_used():
    results = [_om_result(purchase_price=2_500_000.0, exit_cap_rate=0.065)]
    merged, _ = merge_extractions(results)
    assert merged["acquisition"]["purchase_price"] == 2_500_000.0
    assert merged["exit"]["exit_cap_rate"] == 0.065


# ── Rent Roll wins for unit count ────────────────────────────────────────────

def test_rent_roll_num_units_beats_om():
    results = [
        _om_result(purchase_price=1_000_000.0, num_units=200),
        _rr_result(num_units_actual=195),
    ]
    merged, _ = merge_extractions(results)
    assert merged["project"]["num_units"] == 195


# ── Defaults applied ─────────────────────────────────────────────────────────

def test_defaults_applied_when_no_values():
    results = [_om_result(purchase_price=1_000_000.0)]
    merged, _ = merge_extractions(results)
    assert merged["financing"]["ltv_pct"] == 0.70
    assert merged["operational"]["vacancy_credit_loss_pct"] == 0.10
    assert merged["criteria"]["target_irr"] == 0.15


# ── Lease records pass through ───────────────────────────────────────────────

def test_lease_records_from_rent_roll():
    from app.verticals.real_estate.underwriting.schemas.self_storage import LeaseRecord
    rr = RentRollExtraction(
        num_units_actual=10,
        lease_records=[LeaseRecord(monthly_rent=500.0, unit_id="A1")],
    )
    results = [
        _om_result(purchase_price=500_000.0),
        ExtractedDocResult(run_id="r1", job_id="j1", doc_type="rent_roll", rent_roll=rr),
    ]
    merged, _ = merge_extractions(results)
    assert len(merged["lease_records"]) == 1
    assert merged["lease_records"][0]["monthly_rent"] == 500.0
```

- [ ] **Step 2: Run to confirm failures**

```bash
cd backend && python -m pytest tests/unit/verticals/real_estate/underwriting/test_merger.py -v 2>&1 | head -20
```
Expected: ImportError on `merger` module.

- [ ] **Step 3: Create `merger.py`**

```python
"""CRE-standard merge of per-doc extraction results into SelfStorageInputs dict.

Priority rules (industry standard):
- T-12 actuals win for all operating figures (GPR, vacancy, expenses, NOI)
- Rent Roll wins for unit count, occupancy, lease records
- OM wins for deal terms (purchase price, exit cap, hold period, LTV, rate)
- T-6 figures are annualised: value × (12 / period_months)
"""

from __future__ import annotations

from typing import Any, Optional

from app.utils.logging import logger

from .schemas import (
    ExtractedDocResult,
    OMExtraction,
    RentRollExtraction,
    T12Extraction,
)


def merge_extractions(
    results: list[ExtractedDocResult],
) -> tuple[dict, dict]:
    """Merge per-doc extraction results into a SelfStorageInputs-compatible dict.

    Returns:
        (merged_inputs_dict, field_citations_dict)
    """
    om: Optional[OMExtraction] = None
    t12: Optional[T12Extraction] = None
    rr: Optional[RentRollExtraction] = None
    all_citations: dict = {}

    for r in results:
        all_citations.update(r.field_citations or {})
        if r.doc_type == "om" and r.om and not r.error:
            om = r.om
        elif r.doc_type == "t12" and r.t12 and not r.error:
            t12 = r.t12
        elif r.doc_type == "rent_roll" and r.rent_roll and not r.error:
            rr = r.rent_roll

    merged = _build_merged_inputs(om, t12, rr)
    return merged, all_citations


def _build_merged_inputs(
    om: Optional[OMExtraction],
    t12: Optional[T12Extraction],
    rr: Optional[RentRollExtraction],
) -> dict:
    """Apply CRE priority rules and produce a SelfStorageInputs-compatible dict."""

    # T-6 annualisation factor
    t12_factor = 1.0
    if t12 and t12.period_months and t12.period_months > 0 and t12.period_months < 12:
        t12_factor = 12.0 / t12.period_months

    def ann(val: Optional[float]) -> Optional[float]:
        """Annualise a T-12/T-6 value."""
        return val * t12_factor if val is not None else None

    def first(*vals: Any) -> Any:
        """Return first non-None value."""
        return next((v for v in vals if v is not None), None)

    return {
        "project": {
            "name": first(om.name if om else None) or "Untitled Deal",
            "asset_type": "self_storage",
            "address": first(om.address if om else None),
            "num_units": first(
                rr.num_units_actual if rr else None,
                om.num_units if om else None,
            ),
            "rentable_sqft": first(om.rentable_sqft if om else None),
            "year_built": first(om.year_built if om else None),
        },
        "acquisition": {
            "purchase_price": first(om.purchase_price if om else None) or 0.0,
            "closing_cost_pct": first(om.closing_cost_pct if om else None, 0.02),
            "capex_reserve_per_unit": first(om.capex_reserve_per_unit if om else None, 0.0),
        },
        "operational": {
            "gross_potential_rent_annual": first(
                ann(t12.gpr_annual_actual) if t12 else None,
                om.gpr_annual_projected if om else None,
                0.0,
            ),
            "vacancy_credit_loss_pct": first(
                t12.vacancy_credit_loss_pct_actual if t12 else None,
                om.vacancy_pct_projected if om else None,
                0.10,
            ),
            "other_income_annual": first(ann(t12.other_income_annual) if t12 else None, 0.0),
            "rent_growth_pct": first(
                rr.rent_growth_pct if rr else None,
                0.03,
            ),
            "property_tax_annual": first(ann(t12.property_tax_annual) if t12 else None, 0.0),
            "insurance_annual": first(ann(t12.insurance_annual) if t12 else None, 0.0),
            "mgmt_fee_pct": first(
                t12.mgmt_fee_pct_actual if t12 else None,
                om.mgmt_fee_pct if om else None,
                0.08,
            ),
            "payroll_annual": first(ann(t12.payroll_annual) if t12 else None, 0.0),
            "repairs_maintenance_annual": first(ann(t12.repairs_maintenance_annual) if t12 else None, 0.0),
            "utilities_annual": first(ann(t12.utilities_annual) if t12 else None, 0.0),
            "marketing_annual": first(ann(t12.marketing_annual) if t12 else None, 0.0),
            "other_opex_annual": first(ann(t12.other_opex_annual) if t12 else None, 0.0),
            "opex_growth_pct": 0.02,
        },
        "financing": {
            "ltv_pct": first(om.ltv_pct if om else None, 0.70),
            "interest_rate_pct": first(om.interest_rate_pct if om else None, 0.065),
            "amortization_years": first(om.amortization_years if om else None, 25),
            "loan_term_years": first(om.loan_term_years if om else None, 10),
        },
        "exit": {
            "hold_period_years": first(om.hold_period_years if om else None, 10),
            "exit_cap_rate": first(om.exit_cap_rate if om else None, 0.065),
            "selling_cost_pct": first(om.selling_cost_pct if om else None, 0.03),
        },
        "criteria": {
            "target_irr": first(om.target_irr if om else None, 0.15),
            "target_cash_on_cash": first(om.target_cash_on_cash if om else None, 0.08),
            "target_equity_multiple": first(om.target_equity_multiple if om else None, 2.0),
            "max_ltv": 0.80,
        },
        "lease_records": [
            lr.model_dump() for lr in (rr.lease_records if rr else [])
        ],
    }
```

- [ ] **Step 4: Run the merger tests**

```bash
cd backend && python -m pytest tests/unit/verticals/real_estate/underwriting/test_merger.py -v
```
Expected: all 8 tests pass.

---

## Task 8: Update Discrepancy Detection

**Files:**
- Modify: `backend/app/verticals/real_estate/underwriting/extraction/discrepancy.py`

The existing `detect_discrepancies` takes raw dicts. Update it to accept typed `ExtractedDocResult` objects while keeping backward compatibility.

- [ ] **Step 1: Add a new typed entrypoint at the bottom of `discrepancy.py`**

Add after the existing `detect_discrepancies` function:

```python
def detect_discrepancies_from_results(results: list) -> list[dict]:
    """Detect discrepancies from typed ExtractedDocResult list.

    Converts typed models to the flat dict format expected by detect_discrepancies().
    """
    from .schemas import ExtractedDocResult

    om_data: dict = {}
    rent_roll_data: dict = {}
    t12_data: dict = {}

    for r in results:
        if r.doc_type == "om" and r.om and not r.error:
            om_data = r.om.model_dump(exclude_none=True)
            # Remap field names to what detect_discrepancies() expects
            om_data["occupancy_pct"] = om_data.pop("vacancy_pct_projected", None)
            if om_data.get("occupancy_pct") is not None:
                om_data["occupancy_pct"] = 1.0 - om_data["occupancy_pct"]
            om_data["gross_potential_rent_annual"] = om_data.pop("gpr_annual_projected", None)
        elif r.doc_type == "t12" and r.t12 and not r.error:
            t12 = r.t12
            factor = 12.0 / t12.period_months if (t12.period_months and t12.period_months < 12) else 1.0
            t12_data = {
                "summary": {
                    "opex_ratio": None,
                    "total_revenue": (t12.gpr_annual_actual or 0) * factor,
                }
            }
        elif r.doc_type == "rent_roll" and r.rent_roll and not r.error:
            rr = r.rent_roll
            rent_roll_data = {
                "summary": {
                    "total_units": rr.num_units_actual,
                    "occupancy_pct": rr.physical_occupancy_pct,
                    "annual_gross_potential_rent": None,
                }
            }

    return detect_discrepancies(om_data, rent_roll_data, t12_data)
```

- [ ] **Step 2: Verify import**

```bash
cd backend && python -c "
from app.verticals.real_estate.underwriting.extraction.discrepancy import detect_discrepancies_from_results
print('OK')
"
```
Expected: `OK`

---

## Task 9: Rewrite Celery Tasks

**Files:**
- Modify: `backend/app/verticals/real_estate/underwriting/extraction/tasks/tasks.py`

This is a full rewrite. The existing file has the broken chain and large Redis payloads.

- [ ] **Step 1: Replace the entire file**

```python
"""Celery tasks for RE underwriting extraction pipeline.

Design:
- Payloads through Redis contain IDs only — no document content.
- Each re_extract_per_doc_task fetches its own chunks from DB.
- chord(group(N extract tasks), chain(merge, discrepancy, calculate))
  ensures parallel extraction with sequential post-processing.
- soft_time_limit + acks_late + reject_on_worker_lost give resilience
  against worker crashes.
"""

from __future__ import annotations

from celery import chain, chord, group, shared_task
from celery.exceptions import SoftTimeLimitExceeded
from typing import Any

from app.config import settings
from app.database import get_db
from app.repositories.document_repository import DocumentRepository
from app.repositories.re_underwriting_repo import UnderwritingRunRepository
from app.services.job_tracker import JobProgressTracker
from app.services.llm_client import LLMClient
from app.utils.logging import logger

from ..extractor import extract_document
from ..llm_service import REExtractionLLMService
from ..merger import merge_extractions
from ..discrepancy import detect_discrepancies_from_results
from ..schemas import ExtractedDocResult
from ...calculator import calculate
from ...stress_tests import run_stress_tests
from ...rollover import compute_rollover_risk
from ...verdict import evaluate
from ...schemas.self_storage import SelfStorageInputs


def _get_db_session():
    return next(get_db())


def _get_llm_service() -> REExtractionLLMService:
    client = LLMClient(
        api_key=settings.anthropic_api_key,
        model=settings.synthesis_llm_model,
        max_tokens=settings.synthesis_llm_max_tokens,
        timeout_seconds=settings.synthesis_llm_timeout_seconds,
    )
    return REExtractionLLMService(client)


@shared_task(
    bind=True,
    soft_time_limit=settings.re_uw_task_soft_time_limit_seconds,
    acks_late=True,
    reject_on_worker_lost=True,
)
def re_extract_per_doc_task(self, payload: dict) -> dict:
    """Extract structured data from one document. Fetches own chunks from DB.

    Payload: {run_id, job_id, doc_type, document_id}
    Returns: ExtractedDocResult.model_dump() — small JSON, safe for Redis.
    """
    run_id = payload["run_id"]
    job_id = payload["job_id"]
    doc_type = payload["doc_type"]
    document_id = payload["document_id"]
    source_index = payload.get("source_index", 1)

    db = _get_db_session()
    tracker = JobProgressTracker(db, job_id)

    try:
        tracker.update_progress(
            status="extracting",
            current_stage=f"extracting_{doc_type}",
            progress_percent=30,
            message=f"Extracting {doc_type.upper()}...",
        )
        doc_repo = DocumentRepository()
        chunks = doc_repo.get_chunks_for_document(document_id)

        if not chunks:
            logger.warning(f"No chunks found for document {document_id}", extra={"run_id": run_id})
            result = ExtractedDocResult(
                run_id=run_id, job_id=job_id, doc_type=doc_type,
                error=f"No chunks found for document {document_id}",
            )
            return result.model_dump()

        service = _get_llm_service()
        result = extract_document(run_id, job_id, doc_type, chunks, service, source_index)
        return result.model_dump()

    except SoftTimeLimitExceeded:
        logger.error(f"Soft time limit exceeded for {doc_type}", extra={"run_id": run_id})
        tracker.mark_error(
            error_stage="extraction",
            error_message=f"Extraction timed out for {doc_type.upper()}",
            internal_error="SoftTimeLimitExceeded",
            error_type="timeout",
            is_retryable=False,
        )
        raise
    except Exception as e:
        logger.error(f"Extraction failed for {doc_type}: {e}", extra={"run_id": run_id})
        # Non-required docs: return error result, don't fail the whole pipeline
        if doc_type in ("t12", "rent_roll"):
            logger.warning(f"Optional doc {doc_type} failed — continuing pipeline")
            result = ExtractedDocResult(run_id=run_id, job_id=job_id, doc_type=doc_type, error=str(e)[:500])
            return result.model_dump()
        # OM is required — propagate failure
        tracker.mark_error(
            error_stage="extraction",
            error_message="Failed to extract Offering Memorandum",
            internal_error=str(e)[:1000],
            error_type="extraction_error",
            is_retryable=False,
        )
        raise


@shared_task(
    bind=True,
    soft_time_limit=settings.re_uw_task_soft_time_limit_seconds,
    acks_late=True,
    reject_on_worker_lost=True,
)
def re_merge_extractions_task(self, doc_result_dicts: list[dict]) -> dict:
    """Fan-in: merge per-doc extraction results into SelfStorageInputs dict.

    Receives list[ExtractedDocResult.model_dump()] from chord fan-in.
    """
    if not doc_result_dicts:
        raise ValueError("No extraction results to merge")

    run_id = doc_result_dicts[0]["run_id"]
    job_id = doc_result_dicts[0]["job_id"]
    db = _get_db_session()
    tracker = JobProgressTracker(db, job_id)
    repo = UnderwritingRunRepository(db)

    try:
        tracker.update_progress(
            status="extracting", current_stage="merging",
            progress_percent=60, message="Merging extracted data...",
        )
        results = [ExtractedDocResult(**d) for d in doc_result_dicts]
        merged_inputs, field_citations = merge_extractions(results)

        repo.update_inputs(run_id, None, merged_inputs)  # user_id=None — internal call

        return {
            "run_id": run_id,
            "job_id": job_id,
            "merged_inputs": merged_inputs,
            "field_citations": field_citations,
            "doc_results": doc_result_dicts,
        }
    except SoftTimeLimitExceeded:
        tracker.mark_error(
            error_stage="merging", error_message="Merge timed out",
            internal_error="SoftTimeLimitExceeded", error_type="timeout", is_retryable=False,
        )
        raise
    except Exception as e:
        logger.error(f"Merge failed: {e}", extra={"run_id": run_id})
        tracker.mark_error(
            error_stage="merging", error_message="Failed to merge extracted data",
            internal_error=str(e)[:1000], error_type="merge_error", is_retryable=False,
        )
        raise


@shared_task(
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
)
def re_detect_discrepancies_task(self, payload: dict) -> dict:
    """Detect cross-document discrepancies. Non-fatal — logs and continues."""
    run_id = payload["run_id"]
    job_id = payload["job_id"]
    db = _get_db_session()
    tracker = JobProgressTracker(db, job_id)
    repo = UnderwritingRunRepository(db)

    try:
        tracker.update_progress(
            status="extracting", current_stage="discrepancy_detection",
            progress_percent=70, message="Checking for inconsistencies...",
        )
        results = [ExtractedDocResult(**d) for d in payload.get("doc_results", [])]
        discrepancies = detect_discrepancies_from_results(results)

        run = db.get(type("_", (), {"__tablename__": "re_underwriting_runs"})(), run_id)
        # Update discrepancies via repo's raw update
        from sqlalchemy import update
        from app.db_models_re import UnderwritingRun
        db.execute(
            update(UnderwritingRun)
            .where(UnderwritingRun.id == run_id)
            .values(discrepancies=discrepancies, field_citations=payload.get("field_citations", {}))
        )
        db.commit()

        payload["discrepancies"] = discrepancies
        return payload
    except Exception as e:
        logger.warning(f"Discrepancy detection failed (non-fatal): {e}", extra={"run_id": run_id})
        payload["discrepancies"] = []
        return payload


@shared_task(
    bind=True,
    soft_time_limit=settings.re_uw_task_soft_time_limit_seconds,
    acks_late=True,
    reject_on_worker_lost=True,
)
def re_calculate_underwriting_task(self, payload: dict) -> dict:
    """Run calculator, stress tests, rollover risk, verdict. Store result."""
    run_id = payload["run_id"]
    job_id = payload["job_id"]
    db = _get_db_session()
    tracker = JobProgressTracker(db, job_id)
    repo = UnderwritingRunRepository(db)

    try:
        tracker.update_progress(
            status="calculating", current_stage="calculation",
            progress_percent=80, message="Running calculations...",
        )
        inputs = SelfStorageInputs(**payload.get("merged_inputs", {}))
        result = calculate(inputs)
        result.stress_tests = run_stress_tests(inputs)
        if inputs.lease_records:
            result.rollover_risk = compute_rollover_risk(inputs.lease_records)
        verdict = evaluate(result, inputs.criteria, result.stress_tests)

        tracker.update_progress(
            status="completed", current_stage="storage",
            progress_percent=95, message="Storing results...",
        )
        typed_metrics = {
            "irr": result.irr,
            "cash_on_cash": result.cash_on_cash,
            "equity_multiple": result.equity_multiple,
            "dscr_year_one": result.dscr_year_one,
            "ltv": result.ltv,
            "cap_rate_year_one": result.cap_rate_year_one,
            "cap_rate_pro_forma": result.cap_rate_pro_forma,
            "noi_year_one": result.noi_year_one,
            "total_profit": result.total_profit,
            "monthly_cashflow": result.monthly_cashflow,
            "verdict_status": verdict.status,
            "verdict_failures": [f.model_dump() for f in verdict.failures],
        }
        repo.update_result(run_id, result.model_dump(), typed_metrics)
        tracker.update_progress(
            status="completed", current_stage="done",
            progress_percent=100, message="Complete!",
        )
        return {"run_id": run_id, "status": "completed"}

    except SoftTimeLimitExceeded:
        tracker.mark_error(
            error_stage="calculation", error_message="Calculation timed out",
            internal_error="SoftTimeLimitExceeded", error_type="timeout", is_retryable=False,
        )
        repo.update_status(run_id, "failed", "Calculation timed out")
        raise
    except Exception as e:
        logger.error(f"Calculation failed: {e}", extra={"run_id": run_id})
        tracker.mark_error(
            error_stage="calculation", error_message="Calculation failed",
            internal_error=str(e)[:1000], error_type="calculation_error", is_retryable=False,
        )
        repo.update_status(run_id, "failed", str(e)[:500])
        raise


def start_re_underwriting_chain(
    run_id: str,
    doc_specs: list[dict],  # [{document_id, doc_type}]
    job_id: str,
) -> str:
    """Build and launch the underwriting chord.

    doc_specs: list of {document_id: str, doc_type: "om"|"t12"|"rent_roll"}
    Each task receives only IDs — no content passes through Redis.
    """
    payloads = [
        {
            "run_id": run_id,
            "job_id": job_id,
            "doc_type": spec["doc_type"],
            "document_id": spec["document_id"],
            "source_index": i + 1,
        }
        for i, spec in enumerate(doc_specs)
    ]

    chord(
        group(re_extract_per_doc_task.s(p) for p in payloads),
        chain(
            re_merge_extractions_task.s(),
            re_detect_discrepancies_task.s(),
            re_calculate_underwriting_task.s(),
        ),
    ).apply_async(queue="critical")

    logger.info(f"RE underwriting chain started: {run_id}", extra={"doc_count": len(doc_specs)})
    return job_id
```

- [ ] **Step 2: Verify the module imports**

```bash
cd backend && python -c "
from app.verticals.real_estate.underwriting.extraction.tasks.tasks import start_re_underwriting_chain
print('OK')
"
```
Expected: `OK`

---

## Task 10: Fix the API Endpoint

**Files:**
- Modify: `backend/app/verticals/real_estate/api/underwriting.py`

Remove the N+1 chunk fetching loop. Pass only `document_id` + `doc_type` to the Celery chain.

- [ ] **Step 1: Replace the `create_underwriting_run` endpoint body**

Find the `create_underwriting_run` function and replace its body:

```python
@router.post("/runs", response_model=dict)
def create_underwriting_run(
    payload: CreateUnderwritingRunRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    repo = UnderwritingRunRepository(db)
    job_repo = JobRepository()

    # Validate OM is present
    doc_types = [d["doc_type"] for d in payload.documents]
    if "om" not in doc_types:
        raise HTTPException(status_code=400, detail="Offering Memorandum (om) is required")

    try:
        run = repo.create(
            user_id=user.id,
            name=payload.name,
            asset_type=payload.asset_type,
            address=payload.address,
            document_ids=[d["document_id"] for d in payload.documents],
        )
        job_state = job_repo.create_job(
            entity_type="underwriting_run",
            entity_id=run.id,
            status="extracting",
            current_stage="initialization",
            progress_percent=5,
            job_id=run.id,
        )
        if not job_state:
            raise ValueError("Failed to create job state")

        # Pass IDs only — tasks fetch their own chunks
        doc_specs = [
            {"document_id": d["document_id"], "doc_type": d["doc_type"]}
            for d in payload.documents
        ]
        start_re_underwriting_chain(run.id, doc_specs, run.id)

        logger.info(f"Created underwriting run: {run.id}", extra={"user_id": user.id})
        return {"run_id": run.id, "extraction_job_id": run.id, "status": "extracting"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create underwriting run: {e}")
        raise HTTPException(status_code=400, detail=str(e))
```

- [ ] **Step 2: Remove now-unused imports**

Remove `DocumentRepository` from the imports at the top of `underwriting.py` if it's no longer used elsewhere in that file.

- [ ] **Step 3: Verify the endpoint module loads**

```bash
cd backend && python -c "
from app.verticals.real_estate.api.underwriting import router
print('routes:', [r.path for r in router.routes])
"
```
Expected: list of underwriting routes including `/runs`.

---

## Task 11: Add Stale Job Sweep to `periodic_cleanup`

**Files:**
- Modify: `backend/app/core/lifespan.py`

- [ ] **Step 1: Add imports at the top of `lifespan.py`**

Add after existing imports:

```python
from datetime import datetime, timedelta, timezone
```

Check if `datetime` is already imported — add only what's missing.

- [ ] **Step 2: Add the stale sweep inside `periodic_cleanup()`**

Add after the upload cleanup block (before `except asyncio.CancelledError`):

```python
            # Stale underwriting run sweep
            try:
                from app.config import settings as _s
                from app.database import SessionLocal
                from app.db_models_re import UnderwritingRun
                from sqlalchemy import update

                cutoff = datetime.now(timezone.utc) - timedelta(minutes=_s.re_uw_stale_job_timeout_minutes)
                with SessionLocal() as sweep_db:
                    result = sweep_db.execute(
                        update(UnderwritingRun)
                        .where(UnderwritingRun.status == "extracting")
                        .where(UnderwritingRun.created_at < cutoff)
                        .values(
                            status="failed",
                            error_message="Job timed out — worker may have crashed",
                        )
                        .returning(UnderwritingRun.id)
                    )
                    swept = result.fetchall()
                    sweep_db.commit()
                if swept:
                    logger.warning(
                        "Swept stale underwriting runs",
                        extra={"count": len(swept), "run_ids": [r[0] for r in swept]},
                    )
            except Exception as sweep_err:
                logger.error(f"Stale underwriting sweep failed: {sweep_err}", exc_info=True)
```

- [ ] **Step 3: Verify the app starts without errors**

```bash
cd backend && python -c "from app.core.lifespan import periodic_cleanup; print('OK')"
```
Expected: `OK`

---

## Task 12: Run All Unit Tests

- [ ] **Step 1: Run all new unit tests**

```bash
cd backend && python -m pytest tests/unit/verticals/real_estate/underwriting/ -v
```
Expected: all tests pass (3 schema smoke tests + 9 extractor tests + 8 merger tests = 20 tests).

- [ ] **Step 2: Run existing tests to check no regressions**

```bash
cd backend && python -m pytest tests/unit/ -v --ignore=tests/unit/verticals/real_estate/underwriting/ -x 2>&1 | tail -20
```
Expected: no new failures.

- [ ] **Step 3: Check all modules import cleanly**

```bash
cd backend && python -c "
from app.verticals.real_estate.underwriting.extraction.schemas import ExtractedDocResult
from app.verticals.real_estate.underwriting.extraction.extractor import extract_document
from app.verticals.real_estate.underwriting.extraction.merger import merge_extractions
from app.verticals.real_estate.underwriting.extraction.discrepancy import detect_discrepancies_from_results
from app.verticals.real_estate.underwriting.extraction.tasks.tasks import start_re_underwriting_chain
from app.verticals.real_estate.api.underwriting import router
print('All imports OK')
"
```
Expected: `All imports OK`
