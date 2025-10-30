#!/bin/bash
# Quick test script for parser integration

echo "=========================================="
echo "Testing Parser Integration"
echo "=========================================="
echo ""

# Test PDF path
PDF_PATH="tests/data/sample_cims/CIM-04-Alcatel-Lucent.pdf"

if [ ! -f "$PDF_PATH" ]; then
    echo "❌ Test PDF not found: $PDF_PATH"
    exit 1
fi

echo "📄 Using test PDF: $PDF_PATH"
echo ""

# Check if backend is running
if ! curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    echo "❌ Backend is not running on http://localhost:8000"
    echo ""
    echo "Start the backend first:"
    echo "  source venv/bin/activate"
    echo "  uvicorn main:app --reload --port 8000"
    exit 1
fi

echo "✅ Backend is running"
echo ""

# Upload PDF
echo "📤 Uploading PDF to backend..."
echo ""

curl -X POST \
  -F "file=@$PDF_PATH" \
  http://localhost:8000/api/extract \
  -w "\n\nHTTP Status: %{http_code}\n" \
  | jq '.' 2>/dev/null || cat

echo ""
echo "=========================================="
echo "Check database for results:"
echo "  sqlite3 sandcloud_dev.db"
echo "  > SELECT * FROM extractions;"
echo "  > SELECT * FROM parser_outputs;"
echo "=========================================="
