-- Debug script to check document_chunks page numbers for key-value pairs
-- Run this in your postgres client or pgAdmin

-- 1. Check all key_value_pairs chunks and their page numbers
SELECT
    id,
    document_id,
    content,
    metadata->>'page_number' as page_number,
    metadata->>'page_range' as page_range,
    metadata->>'section_type' as section_type,
    metadata
FROM document_chunks
WHERE section_type = 'key_value_pairs'
ORDER BY (metadata->>'page_number')::int;

-- 2. Search for "Price" specifically in key_value chunks
SELECT
    id,
    document_id,
    content,
    metadata->>'page_number' as page_number,
    metadata
FROM document_chunks
WHERE section_type = 'key_value_pairs'
  AND (content ILIKE '%price%' OR content ILIKE '%2,500,000%' OR content ILIKE '%2500000%')
ORDER BY id;

-- 3. Check ALL chunks (including tables) that mention Price
SELECT
    id,
    document_id,
    section_type,
    content,
    metadata->>'page_number' as page_number,
    metadata->>'table_name' as table_name
FROM document_chunks
WHERE content ILIKE '%price%'
   OR content ILIKE '%2,500,000%'
   OR content ILIKE '%2500000%'
ORDER BY (metadata->>'page_number')::int, id;
