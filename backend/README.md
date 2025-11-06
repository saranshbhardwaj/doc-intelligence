# Document Intelligence Backend

> Modular, production-ready document parsing system for extracting structured data from CIM (Confidential Information Memorandum) PDFs using Claude AI.

## 🚀 Quick Start (5 minutes)

### 1. Installation

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment Setup

```bash
cp .env.example .env
# Edit .env and add your API keys:
# - ANTHROPIC_API_KEY (required)
# - LLMWHISPERER_API_KEY (optional - for OCR)
```

### 3. Initialize Database

```bash
python -c "from app.database import init_db; init_db()"
```

### 4. Run Backend

```bash
uvicorn main:app --reload --port 8000
```

### 5. Test with Sample PDF

```bash
# In another terminal
./quick_test.sh
```

**Expected Output:**
```json
{
  "data": {
    "company_info": { "company_name": "...", ... },
    "financials": { "revenue_by_year": {...}, ... },
    ...
  },
  "metadata": {
    "pages": 64,
    "characters_extracted": 157960,
    "processing_time_seconds": 3.2
  }
}
```

---

## 📚 Table of Contents

- [Architecture](#architecture)
- [Configuration](#configuration)
- [Parser System](#parser-system)
- [Testing](#testing)
- [Database](#database)
- [API Endpoints](#api-endpoints)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)

---

## 🏗️ Architecture

### System Overview

```
┌─────────────────┐
│   FastAPI App   │
└────────┬────────┘
         │
    ┌────┴────┐
    │ Extract │ (/api/extract)
    │  API    │
    └────┬────┘
         │
    ┌────┴─────────────┐
    │  Parser Factory  │ (Selects parser based on tier + PDF type)
    └────┬─────────────┘
         │
    ┌────┴──────────────────────┐
    │                           │
┌───┴──────┐          ┌────────┴────────┐
│ PyMuPDF  │          │  LLMWhisperer   │
│  (Free)  │          │   (Paid OCR)    │
└───┬──────┘          └────────┬────────┘
    │                          │
    └──────────┬───────────────┘
               │
          ┌────┴─────┐
          │   Text   │
          └────┬─────┘
               │
          ┌────┴─────┐
          │  Claude  │ (Structure extraction)
          │   API    │
          └────┬─────┘
               │
          ┌────┴─────┐
          │   JSON   │
          │  Output  │
          └──────────┘
```

### Key Components

#### 1. **Parser System** (`app/services/parsers/`)
- **Base Class** ([base.py](app/services/parsers/base.py)) - Abstract parser interface
- **PyMuPDF Parser** ([pymupdf_parser.py](app/services/parsers/pymupdf_parser.py)) - Free, digital PDFs
- **LLMWhisperer Parser** ([llmwhisperer_parser.py](app/services/parsers/llmwhisperer_parser.py)) - Paid OCR
- **Parser Factory** ([parser_factory.py](app/services/parsers/parser_factory.py)) - Smart parser selection

#### 2. **Database Layer** (`app/database.py`, `app/db_models.py`)
- SQLite (development) / PostgreSQL (production)
- Tables: `extractions`, `parser_outputs`, `cache_entries`, `rate_limits`
- Automatic migration support

#### 3. **LLM Client** (`app/services/llm_client.py`)
- Claude API integration
- Smart text truncation (80/20 split)
- Structured JSON extraction

#### 4. **Cache System** (`app/services/cache.py`)
- SHA256-based file content hashing
- Persistent disk cache (`logs/cache/`)
- Prevents duplicate processing

---

## ⚙️ Configuration

All settings are configurable via `.env` file. No hardcoded values!

### Core Settings

```bash
# API Keys
ANTHROPIC_API_KEY=sk-ant-...
LLMWHISPERER_API_KEY=your-key-here  # Optional

# Database (leave empty for SQLite)
DATABASE_URL=  # or postgresql://localhost/sandcloud_dev

# Environment
ENVIRONMENT=development  # or production
```

### Parser Configuration

```bash
# Free Tier Strategy
PARSER_FREE_DIGITAL=pymupdf     # Fast, free
PARSER_FREE_SCANNED=none        # Not supported

# Pro Tier Strategy
PARSER_PRO_DIGITAL=pymupdf      # Cost optimization
PARSER_PRO_SCANNED=llmwhisperer # OCR for scanned PDFs

# Enterprise Tier Strategy
PARSER_ENTERPRISE_DIGITAL=llmwhisperer    # Consistent quality
PARSER_ENTERPRISE_SCANNED=llmwhisperer
```

### LLM Settings

```bash
LLM_MODEL=claude-sonnet-4-5-20250929
LLM_MAX_TOKENS=16000            # Max output tokens
LLM_MAX_INPUT_CHARS=130000      # Input truncation limit (~30K tokens)
LLM_TIMEOUT_SECONDS=300         # 5 minute timeout
```

**Note:** If your documents are being truncated (check logs for "Document truncated" warnings), increase `LLM_MAX_INPUT_CHARS` to 180000 or 250000.

### LLMWhisperer Settings

```bash
LLMWHISPERER_MODE=low_cost           # native_text | low_cost | high_quality
LLMWHISPERER_TIMEOUT_SECONDS=300     # OCR can be slow
LLMWHISPERER_MEDIAN_FILTER_SIZE=0    # Noise removal (0=off, 3-9=on)
```

**Pricing:**
- `native_text`: $0.001/page ($1/1000 pages)
- `low_cost`: $0.005/page ($5/1000 pages) - **Recommended**
- `high_quality`: $0.010/page ($10/1000 pages)
- `form_elements`: $0.015/page ($15/1000 pages)

### Rate Limits

```bash
# Free Tier
RATE_LIMIT_FREE_DAILY=2
RATE_LIMIT_FREE_MONTHLY=60

# Pro Tier
RATE_LIMIT_PRO_DAILY=50
RATE_LIMIT_PRO_MONTHLY=1500

# Enterprise Tier (-1 = unlimited)
RATE_LIMIT_ENTERPRISE_DAILY=-1
RATE_LIMIT_ENTERPRISE_MONTHLY=-1
```

### Testing Overrides

```bash
# Force specific parser (bypasses tier logic)
FORCE_PARSER=llmwhisperer  # or pymupdf or empty

# Force specific tier
FORCE_USER_TIER=pro  # or free, enterprise, or empty

# WARNING: Only use for testing! Leave empty in production!
```

---

## 🔧 Parser System

### How Parser Selection Works

```python
# Automatic selection based on user tier + PDF type
def get_parser(user_tier: str, pdf_bytes: bytes) -> DocumentParser:
    is_scanned = detect_scanned_pdf(pdf_bytes)
    pdf_type = "scanned" if is_scanned else "digital"

    parser_config = {
        "free": {
            "digital": "pymupdf",
            "scanned": None  # Upgrade required
        },
        "pro": {
            "digital": "pymupdf",      # Use free for digital
            "scanned": "llmwhisperer"  # Paid OCR for scanned
        },
        "enterprise": {
            "digital": "llmwhisperer",   # Consistent quality
            "scanned": "llmwhisperer"
        }
    }

    parser_name = parser_config[user_tier][pdf_type]
    return create_parser(parser_name)
```

### PDF Type Detection

```python
# Samples first 3 pages to determine if PDF is scanned
def detect_scanned_pdf(pdf_bytes: bytes) -> bool:
    # Extract text from first 3 pages
    # If < 100 chars/page → scanned (images only)
    # If >= 100 chars/page → digital (has text layer)
```

### Adding a New Parser

1. **Create parser class** in `app/services/parsers/`:
```python
from .base import DocumentParser, ParserOutput

class MyNewParser(DocumentParser):
    @property
    def name(self) -> str:
        return "mynewparser"

    def parse(self, pdf_bytes: bytes) -> ParserOutput:
        # Your parsing logic here
        text = extract_text(pdf_bytes)
        return ParserOutput(
            text=text,
            page_count=count_pages(pdf_bytes),
            parser_name=self.name,
            processing_time_ms=elapsed_ms
        )
```

2. **Register in factory** (`parser_factory.py`):
```python
def create_parser(parser_name: str) -> DocumentParser:
    if parser_name == "mynewparser":
        return MyNewParser()
```

3. **Update config** (`.env`):
```bash
PARSER_PRO_DIGITAL=mynewparser
```

---

## 🧪 Testing

### Quick Test Script

```bash
./quick_test.sh
```

**What it does:**
1. Checks if backend is running
2. Uploads `CIM-04-Alcatel-Lucent.pdf`
3. Shows extraction results
4. Stores in database

### Manual Testing

```bash
# Test with specific PDF
curl -X POST \
  -F "file=@/path/to/your.pdf" \
  http://localhost:8000/api/extract \
  | jq

# Test with PyMuPDF (free)
FORCE_PARSER=pymupdf uvicorn main:app --reload

# Test with LLMWhisperer (paid OCR)
FORCE_PARSER=llmwhisperer uvicorn main:app --reload
```

### Parser Comparison Test

```bash
# Run comparison between parsers (no LLM call)
python scripts/compare_parsers.py tests/data/sample_cims/CIM-06-Pizza-Hut.pdf
```

Shows:
- Pages detected
- Characters extracted
- Processing time
- Text quality
- Cost

### Inspection Script

```bash
# Quick inspection of extraction results
./scripts/quick_check.sh /tmp/result.json
```

Shows:
- Company name
- Revenue years
- Management team count
- Key risks count
- Processing metadata

### Test Data

Sample CIMs are in `tests/data/sample_cims/`:
- CIM-01-Consolidated-Utility-Services.pdf
- CIM-02-American-Casino.pdf
- CIM-04-Alcatel-Lucent.pdf
- CIM-05-Arion-Banki-hf.pdf
- CIM-06-Pizza-Hut.pdf

See [tests/README.md](tests/README.md) for testing strategy and quality benchmarks.

---

## 💾 Database

### Tables

#### 1. `extractions`
Tracks all document processing requests.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| user_id | String | User identifier (IP or authenticated user) |
| filename | String | Original filename |
| pages | Integer | Page count |
| characters_extracted | Integer | Total characters |
| processing_time_seconds | Float | Total processing time |
| parser_used | String | Which parser was used |
| llm_cost_usd | Float | Claude API cost |
| parsing_cost_usd | Float | Parser cost (LLMWhisperer) |
| created_at | Timestamp | When processed |

#### 2. `parser_outputs`
Raw parser outputs for debugging.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| extraction_id | UUID | FK to extractions |
| parser_name | String | Parser used |
| raw_text | Text | Extracted text |
| page_count | Integer | Pages detected |
| processing_time_ms | Integer | Parser time |

#### 3. `cache_entries`
Cache metadata (files stored on disk).

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| content_hash | String | SHA256 hash of PDF |
| file_path | String | Path to cached file |
| created_at | Timestamp | When cached |
| last_accessed_at | Timestamp | Last access |
| hit_count | Integer | Cache hits |

#### 4. `rate_limits`
Per-user rate limiting.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| user_id | String | User identifier |
| uploads_today | Integer | Today's upload count |
| uploads_this_month | Integer | This month's count |
| last_upload | Timestamp | Last upload time |
| tier | String | free, pro, enterprise |

### Queries

```bash
# Connect to database
sqlite3 sandcloud_dev.db

# View recent extractions
SELECT filename, pages, parser_used, created_at
FROM extractions
ORDER BY created_at DESC
LIMIT 10;

# Check costs
SELECT
  DATE(created_at) as date,
  COUNT(*) as docs,
  SUM(llm_cost_usd) as llm_cost,
  SUM(parsing_cost_usd) as parsing_cost,
  SUM(llm_cost_usd + parsing_cost_usd) as total_cost
FROM extractions
GROUP BY DATE(created_at)
ORDER BY date DESC;

# View cache hit rate
SELECT
  COUNT(*) as total_entries,
  SUM(hit_count) as total_hits,
  ROUND(AVG(hit_count), 2) as avg_hits_per_entry
FROM cache_entries;
```

---

## 📡 API Endpoints

### `POST /api/extract`

Upload a PDF and extract structured data.

**Request:**
```bash
curl -X POST \
  -F "file=@document.pdf" \
  -F "file_label=optional-label" \
  http://localhost:8000/api/extract
```

**Response (200 OK):**
```json
{
  "data": {
    "company_info": {
      "company_name": "NPC International, Inc.",
      "industry": "Quick Service Restaurant",
      "headquarters": "Overland Park, KS",
      "confidence": 0.95
    },
    "financials": {
      "revenue_by_year": {
        "2020": 150000000,
        "2021": 175000000
      },
      "confidence": 0.9
    },
    ...
  },
  "metadata": {
    "request_id": "uuid",
    "filename": "document.pdf",
    "pages": 64,
    "characters_extracted": 157960,
    "processing_time_seconds": 3.2,
    "parser_used": "pymupdf",
    "is_scanned_pdf": false,
    "llm_usage": {
      "input_tokens": 32500,
      "output_tokens": 4200,
      "cost_usd": 0.16
    }
  }
}
```

**Error Responses:**

```json
// 400 Bad Request - No file
{"detail": "No file uploaded"}

// 400 Bad Request - Invalid file type
{"detail": "Only PDF files are supported"}

// 402 Payment Required - Scanned PDF on free tier
{"detail": "Scanned PDFs require Pro or Enterprise tier"}

// 429 Too Many Requests - Rate limit exceeded
{"detail": "Rate limit exceeded"}

// 500 Internal Server Error
{"detail": "Processing failed: <error message>"}
```

### `GET /api/health`

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-10-28T22:00:00",
  "environment": "development",
  "anthropic_configured": true,
  "cache_entries": 15
}
```

---

## 🚢 Deployment

### Environment Variables for Production

```bash
# Production settings
ENVIRONMENT=production
DATABASE_URL=postgresql://user:pass@host:5432/dbname

# Security
ADMIN_API_KEY=generate-secure-random-key

# CORS (update with your domains)
CORS_ORIGINS=["https://your-frontend.vercel.app","https://yourdomain.com"]

# Disable testing overrides
FORCE_PARSER=
FORCE_USER_TIER=

# Higher rate limits for production
RATE_LIMIT_UPLOADS=100
RATE_LIMIT_WINDOW_HOURS=24
```

### Docker Deployment

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Database Migration

```bash
# Export from SQLite
sqlite3 sandcloud_dev.db .dump > backup.sql

# Import to PostgreSQL
psql $DATABASE_URL < backup.sql
```

---

## 🐛 Troubleshooting

### "Document truncated" Warning

**Problem:** Your PDFs are larger than `LLM_MAX_INPUT_CHARS`.

**Solution:** Increase the limit in `.env`:
```bash
LLM_MAX_INPUT_CHARS=180000  # or 250000 for large docs
```

### Parser Not Detecting Pages

**Problem:** LLMWhisperer only detecting partial pages.

**Solution:**
1. Check logs: `grep "LLMWhisperer extracted" logs/app.log`
2. Contact LLMWhisperer support if issue persists
3. Use PyMuPDF for digital PDFs (better page detection)

### Rate Limit Issues in Development

**Problem:** Hitting rate limits during testing.

**Solution:**
```bash
# In .env
RATE_LIMIT_UPLOADS=1000  # High limit for testing
```

### Backend Won't Start

**Problem:** Port 8000 already in use.

**Solution:**
```bash
# Find process
lsof -i :8000

# Kill it
kill -9 <PID>

# Or use different port
uvicorn main:app --reload --port 8001
```

### LLMWhisperer Timeout

**Problem:** OCR taking too long.

**Solution:**
```bash
# In .env
LLMWHISPERER_TIMEOUT_SECONDS=600  # 10 minutes
```

### Cache Not Working

**Problem:** Same PDF being processed multiple times.

**Solution:**
```bash
# Check cache directory
ls -lh logs/cache/

# Clear cache if needed
rm logs/cache/*.json
```

---

## 📝 Logs

All logs stored in `logs/` directory:

```
logs/
├── app.log              # Main application log
├── cache/               # Cached extraction results
├── parsed/              # Parsed JSON outputs
├── raw/                 # Raw extracted text
└── raw_llm_response/    # Claude's raw JSON responses
```

**Viewing Logs:**
```bash
# Follow live logs
tail -f logs/app.log

# Search for errors
grep ERROR logs/app.log

# Check recent extractions
grep "Parser completed" logs/app.log | tail -10

# View truncation warnings
grep "Document truncated" logs/app.log
```

---

## 🤝 Contributing

When adding new features:

1. ✅ Add configuration to `.env` (no hardcoded values)
2. ✅ Update this README
3. ✅ Add tests in `tests/`
4. ✅ Document in code with clear comments
5. ✅ Log important events (INFO level)

---

## 📄 License

Internal use only. Not licensed for external distribution.

---

## 🔗 Quick Links

- [Test Data README](tests/README.md) - Testing strategy and quality benchmarks
- [Quick Test Script](quick_test.sh) - Fast testing workflow
- [Inspection Script](scripts/quick_check.sh) - JSON result inspection

---

**Built with:** FastAPI • Claude AI • SQLAlchemy • PyMuPDF • LLMWhisperer
