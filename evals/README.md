# RE Template Fill — promptfoo Evals

Evaluates the LLM stages of the template fill pipeline against structural assertions.
Test fixtures are exported from real fill runs stored in the database.

## Setup

```bash
npm install -g promptfoo
# or use without installing: npx promptfoo
```

## Workflow

### 1. Run a fill to produce io_log data

Complete at least one fill run end-to-end. The `llm_io_log` column on `template_fill_runs` must be populated.

### 2. Export test fixtures

```bash
cd backend
python -m scripts.export_eval_dataset --output ../evals/datasets
```

Options:
- `--stage all|detect_fields|extract_schema_fields|auto_map_fields|extract_table_values_rag_single`
- `--limit N` — process only the N most recent fill runs
- `--version v1` — override which prompt version to use for system prompt reconstruction

### 3. Run evals

```bash
cd evals

# Single stage
npx promptfoo eval --tests datasets/extract_schema_fields.jsonl

# All stages (update promptfoo.yaml tests: field first)
npx promptfoo eval

# View results in browser
npx promptfoo view
```

## Prompt version comparison (v1 → v2)

```bash
# 1. Create prompts/v2.py, register in prompts/__init__.py

# 2. Export with v2 system prompts
cd backend
python -m scripts.export_eval_dataset --version v2 --output ../evals/datasets/v2

# 3. Compare: run v1 baseline then v2
cd ../evals
npx promptfoo eval --tests datasets/extract_schema_fields.jsonl --output results/v1.json
npx promptfoo eval --tests datasets/v2/extract_schema_fields.jsonl --output results/v2.json
npx promptfoo view
```

## Files

| File | Purpose |
|------|---------|
| `promptfoo.yaml` | Main config — providers, prompts, default test file |
| `.gitignore` | Ignores `datasets/` (contain actual offering memo text) |
| `datasets/*.jsonl` | Generated test fixtures (gitignored) |

## Assertions

Each stage asserts structural validity of the LLM output:

| Stage | Assertions |
|-------|-----------|
| `detect_fields` | is-json, `fields` array, `total_fields` number, confidence in [0,1] |
| `extract_schema_fields` | is-json, `results` array, `total_found` number, confidence in [0,1] |
| `extract_table_values_rag_single` | is-json, `results` array, `total_tables` number |
| `auto_map_fields` | is-json, `mappings` array, `total_mapped` number, confidence in [0,1] |
