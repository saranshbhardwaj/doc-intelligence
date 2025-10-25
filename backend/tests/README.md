# Testing Strategy for CIM Extraction Quality

## Overview

Testing LLM prompt quality requires balancing cost, coverage, and confidence. This guide provides a practical approach for validating extraction quality during MVP development.

## Directory Structure

```
tests/
├── data/
│   ├── sample_cims/          # Test PDF files
│   │   ├── saas_company.pdf
│   │   ├── manufacturing.pdf
│   │   ├── healthcare.pdf
│   │   └── ...
│   │
│   └── golden_outputs/       # Verified correct outputs
│       ├── saas_company.json
│       ├── manufacturing.json
│       └── ...
│
└── README.md                 # This file

scripts/
├── test_extraction_quality.py      # Validation & comparison
└── check_extraction_coverage.py    # Coverage analysis
```

## How Many Documents to Test?

### **Recommended: 5-10 Diverse CIMs**

Quality over quantity! Focus on **diversity**, not volume:

| Category | Why Important | Example |
|----------|---------------|---------|
| **Industry** | Different terminology, metrics | SaaS, Manufacturing, Healthcare, Retail |
| **Deal Size** | Complexity varies | $5M startup, $50M mid-market, $500M enterprise |
| **Document Quality** | Real-world messiness | Clean formatting vs poor scans |
| **Page Count** | Token usage, completeness | 15 pages (simple) vs 60 pages (complex) |
| **Structure** | Different layouts | Slide deck vs report vs hybrid |

**Cost estimate**: 10 documents × $0.17 = **$1.70 for comprehensive testing**

### Why Not More?

- CIMs follow standard formats (investment banking templates)
- Diminishing returns after 10 diverse samples
- Better to test thoroughly on 10 than superficially on 50
- Can always add more if issues arise

## Testing Workflow

### Phase 1: Generate Golden Dataset (ONE TIME)

**Cost: ~$0.85 for 5 documents**

1. Collect 5-10 diverse sample CIMs
2. Place in `tests/data/sample_cims/`
3. Process through your API:
   ```bash
   # Upload via frontend or curl
   curl -X POST http://localhost:8000/api/extract \
     -F "file=@tests/data/sample_cims/saas_company.pdf" \
     > tests/data/golden_outputs/saas_company.json
   ```
4. **MANUALLY REVIEW** each output for accuracy
5. Fix any errors in the JSON (this becomes your "golden" reference)

### Phase 2: Validate Structure (FREE)

**No API calls = $0 cost**

Check that all outputs match expected schema:

```bash
python scripts/test_extraction_quality.py --mode=validate
```

This validates:
- ✓ JSON structure matches Pydantic models
- ✓ Required fields are present
- ✓ Data types are correct
- ✓ Confidence scores are reasonable

### Phase 3: Check Coverage (FREE)

**No API calls = $0 cost**

Analyze which fields are being extracted consistently:

```bash
python scripts/check_extraction_coverage.py tests/data/golden_outputs/*.json
```

Shows:
- Which fields are populated across documents
- Average values (e.g., "3.2 risks per document")
- Fields with low coverage (<50%)
- Recommendations for improvement

### Phase 4: Regression Testing (Only When Needed)

**Cost: $0.85 per test run**

When you change prompts, re-run extraction and compare:

```bash
# 1. Extract with new prompt
curl -X POST http://localhost:8000/api/extract \
  -F "file=@tests/data/sample_cims/saas_company.pdf" \
  > tests/data/new_outputs/saas_company_v2.json

# 2. Compare against golden
python scripts/test_extraction_quality.py --mode=compare \
  --golden tests/data/golden_outputs/saas_company.json \
  --new tests/data/new_outputs/saas_company_v2.json
```

Shows:
- 🔴 HIGH severity differences (revenue, pricing)
- 🟡 MEDIUM severity differences (company name, dates)
- 🟢 LOW severity differences (descriptions, confidence)

## What to Look For

### Critical Fields (Must Be Accurate)

- ✓ Company name
- ✓ Revenue figures (historical + projected)
- ✓ EBITDA/profitability
- ✓ Asking price / valuation
- ✓ Transaction structure
- ✓ Key financial ratios

### Important Fields (Should Be Present)

- ✓ Industry classification
- ✓ Key risks (at least 3-5)
- ✓ Management team
- ✓ Customer concentration
- ✓ Market analysis
- ✓ Growth metrics

### Nice-to-Have Fields

- Balance sheet details
- Operating metrics
- Strategic rationale
- Provenance tracking

## Quality Benchmarks

### Excellent Extraction (Ready for Users)
- ✓ 95%+ accuracy on critical financial fields
- ✓ 80%+ coverage on important fields
- ✓ Confidence scores > 0.7 on average
- ✓ Handles 5/5 diverse test documents well

### Good Extraction (Needs Minor Tweaks)
- ✓ 85%+ accuracy on critical fields
- ✓ 70%+ coverage on important fields
- ⚠ Some formatting inconsistencies
- ⚠ Struggles with 1-2 edge cases

### Poor Extraction (Need Prompt Work)
- ✗ <80% accuracy on critical fields
- ✗ Missing key sections frequently
- ✗ Confidence scores < 0.6
- ✗ Fails on >2 test documents

## Cost Management

### Development Phase
- Use `MOCK_MODE=True` for frontend/UI work (FREE)
- Generate golden dataset once ($0.85)
- Validate/check coverage unlimited (FREE)
- Only re-run extractions when changing prompts (~$0.85 per iteration)

### Testing Budget
| Activity | Frequency | Cost |
|----------|-----------|------|
| Initial golden dataset | Once | $0.85 |
| Prompt iteration test | Per change | $0.85 |
| Structure validation | Unlimited | FREE |
| Coverage checks | Unlimited | FREE |
| **10 prompt iterations** | Development | **~$8.50** |

## Real-World Validation

Beyond automated testing, manually verify:

1. **Spot Check**: Pick 2-3 fields from each document, verify against PDF
2. **Edge Cases**: Test with intentionally difficult documents
3. **User Feedback**: When real users report issues, add to test suite
4. **Confidence Calibration**: Are high-confidence fields actually accurate?

## When to Update Golden Dataset

Regenerate golden outputs when:
- ✓ You significantly change the prompt structure
- ✓ You update the Pydantic models (new fields)
- ✓ You discover systematic errors in current golden data
- ✓ You want to add new test documents

## Quick Start

```bash
# 1. Set up directories
mkdir -p tests/data/sample_cims
mkdir -p tests/data/golden_outputs

# 2. Add sample CIMs (get 5-10 diverse documents)
cp ~/Downloads/sample_cim.pdf tests/data/sample_cims/

# 3. Generate golden dataset
# Upload via your frontend and save responses

# 4. Validate structure
python scripts/test_extraction_quality.py --mode=validate

# 5. Check coverage
python scripts/check_extraction_coverage.py tests/data/golden_outputs/*.json

# 6. Iterate on prompts and re-test
```

## Tips for Cost-Effective Testing

1. **Start with 3 documents** - Add more if you find gaps
2. **Use mock mode** during UI development
3. **Cache is your friend** - Re-uploading same doc is free (cache hit)
4. **Batch prompt changes** - Test 5 changes at once, not one at a time
5. **Manual review is critical** - Don't trust golden data until you verify it

## Next Steps After Testing

Once you have consistent quality:
1. Deploy to production with confidence
2. Add logging for user corrections/feedback
3. Build feedback loop for continuous improvement
4. Consider A/B testing different prompts with real users

---

**Remember**: 5-10 well-chosen test documents with manual verification beats 100 untested documents!
