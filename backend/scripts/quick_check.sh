#!/bin/bash
# Quick check of extracted data

if [ -z "$1" ]; then
    echo "Usage: ./quick_check.sh <json_file>"
    exit 1
fi

FILE=$1

echo "========================================"
echo "QUICK EXTRACTION CHECK"
echo "========================================"
echo ""

echo "Company Info:"
echo "  Name: $(jq -r '.data.company_info.company_name // "NOT FOUND"' "$FILE")"
echo "  Industry: $(jq -r '.data.company_info.industry // "NOT FOUND"' "$FILE")"
echo ""

echo "Financials:"
echo "  Currency: $(jq -r '.data.financials.currency // "NOT FOUND"' "$FILE")"
echo "  Revenue Years: $(jq -r '.data.financials.revenue_by_year | keys | join(", ") // "NOT FOUND"' "$FILE")"
echo "  Latest Revenue: $(jq -r '.data.financials.revenue_by_year | to_entries | max_by(.key) | .value // "NOT FOUND"' "$FILE")"
echo ""

echo "Transaction:"
echo "  Asking Price: $(jq -r '.data.transaction_details.asking_price // "NOT FOUND"' "$FILE")"
echo "  Deal Type: $(jq -r '.data.transaction_details.deal_type // "NOT FOUND"' "$FILE")"
echo ""

echo "Risks:"
RISK_COUNT=$(jq -r '.data.key_risks | length // 0' "$FILE")
echo "  Count: $RISK_COUNT"
if [ "$RISK_COUNT" -gt 0 ]; then
    echo "  First Risk: $(jq -r '.data.key_risks[0].risk // "N/A"' "$FILE")"
fi
echo ""

echo "Management Team:"
TEAM_COUNT=$(jq -r '.data.management_team | length // 0' "$FILE")
echo "  Count: $TEAM_COUNT"
if [ "$TEAM_COUNT" -gt 0 ]; then
    echo "  CEO/First: $(jq -r '.data.management_team[0].name // "N/A"' "$FILE") - $(jq -r '.data.management_team[0].title // "N/A"' "$FILE")"
fi
echo ""

echo "Metadata:"
echo "  Pages: $(jq -r '.metadata.pages // "NOT FOUND"' "$FILE")"
echo "  Processing Time: $(jq -r '.metadata.processing_time_seconds // "NOT FOUND"' "$FILE")s"
echo "  Characters: $(jq -r '.metadata.characters_extracted // "NOT FOUND"' "$FILE")"
echo ""

echo "========================================"
