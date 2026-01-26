# PDF Highlighting Implementation Plan
## Using Azure DI Bounding Regions for Precise Citation Navigation

---

## Executive Summary

Enable precise PDF highlighting by capturing and utilizing bounding region coordinates from Azure Document Intelligence. When users click on citations, the PDF viewer will automatically navigate to and highlight the exact location of the extracted data.

**Current State**: Citations show page numbers only - users must manually find content
**Target State**: Citations navigate to exact location with visual highlight overlay

**Feasibility**: ✅ **HIGH** - ~70% of infrastructure already exists
**Complexity**: 🟡 **MODERATE** - Mainly frontend coordinate transformation work
**Value**: 🟢 **HIGH** - Significantly improves UX for data verification

---

## 1. Architecture Overview

### Data Flow: Azure DI → Database → Frontend

```
┌─────────────────────────────────────────────────────────────────┐
│  1. AZURE DI API RESPONSE                                       │
│  ✅ Already provides bounding_regions with polygon coordinates   │
└────────────────────┬────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│  2. PARSER (azure_document_intelligence_parser.py)              │
│  ✅ Already extracts bounding_regions into structured_data       │
└────────────────────┬────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│  3. SMART CHUNKER (azure_smart_chunker.py)                      │
│  ❌ GAP: Doesn't propagate bounding_regions to chunk metadata   │
│  📝 TODO: Extract polygon coordinates and convert to bbox       │
└────────────────────┬────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│  4. DATABASE (DocumentChunk.chunk_metadata JSONB)               │
│  ✅ Already supports bbox field with ChunkMetadataBuilder       │
└────────────────────┬────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│  5. CITATION RESOLVER (services/citations.py)                   │
│  ✅ Already returns bbox from chunk_metadata                    │
└────────────────────┬────────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│  6. FRONTEND PDF VIEWER (components/pdf/PDFViewer.jsx)          │
│  ❌ GAP: No highlight overlay rendering                         │
│  📝 TODO: Add canvas layer for bbox highlighting                │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Understanding Bounding Regions

### Azure DI Polygon Format

Each bounding region contains a **polygon** array with 8 floats representing 4 (x, y) coordinate pairs:

```json
{
  "bounding_regions": [
    {
      "page_number": 4,
      "polygon": [
        5.7685, 1.5827,  // Top-left (x1, y1)
        8.5918, 1.5771,  // Top-right (x2, y2)
        8.5918, 2.3187,  // Bottom-right (x3, y3)
        5.7685, 2.3187   // Bottom-left (x4, y4)
      ]
    }
  ]
}
```

**Coordinate System**: Inches from top-left origin (0, 0) of the page
- Standard US Letter: 8.5 x 11 inches
- Coordinates are precise to 4 decimal places

### Converting Polygon to BBox

For storage efficiency and rendering simplicity, we'll convert polygons to rectangular bounding boxes:

```python
def polygon_to_bbox(polygon: List[float]) -> Dict:
    """Convert 8-point polygon to rectangular bbox."""
    x_coords = [polygon[i] for i in range(0, 8, 2)]  # [x1, x2, x3, x4]
    y_coords = [polygon[i] for i in range(1, 8, 2)]  # [y1, y2, y3, y4]

    return {
        "x0": min(x_coords),  # Left edge
        "y0": min(y_coords),  # Top edge
        "x1": max(x_coords),  # Right edge
        "y1": max(y_coords)   # Bottom edge
    }
```

**Storage Format** (already supported by ChunkMetadataBuilder):
```python
{
  "bbox": {
    "page": 4,
    "x0": 5.7685,
    "y0": 1.5771,
    "x1": 8.5918,
    "y1": 2.3187
  }
}
```

---

## 3. Implementation Phases

### Phase 1: Backend - Capture Bounding Regions ⭐ HIGH PRIORITY

**Goal**: Propagate bounding regions from parser through chunker to database

**Files to Modify**:
1. `backend/app/services/chunkers/azure_smart_chunker.py` (~100 lines)
2. `backend/app/utils/chunk_metadata.py` (add helper if needed)

**Changes**:

#### A. Add bbox extraction to `_create_section_chunk()` (lines 256-318)

```python
def _create_section_chunk(
    self,
    section: SectionGroup,
    sequence: int,
    total: int,
    parent_chunk_id: Optional[str] = None
) -> Chunk:
    """Create a chunk for a section (or part of a section)."""

    # ... existing code ...

    builder = ChunkMetadataBuilder()
    builder.set_section_id(section.section_id)
    builder.set_sequence(sequence, total)

    # NEW: Extract bounding regions from section paragraphs
    bbox = self._calculate_section_bbox(section)
    if bbox:
        builder.set_bbox(
            page=bbox["page"],
            x0=bbox["x0"],
            y0=bbox["y0"],
            x1=bbox["x1"],
            y1=bbox["y1"]
        )

    # ... rest of existing code ...
```

#### B. Add helper method `_calculate_section_bbox()` (NEW)

```python
def _calculate_section_bbox(self, section: SectionGroup) -> Optional[Dict]:
    """
    Calculate bounding box for a section from its paragraph bounding regions.

    Strategy:
    - Collect all bounding_regions from section paragraphs
    - Convert polygons to bbox coordinates (x0, y0, x1, y1)
    - Merge into single bbox covering the entire section

    Returns:
        Dict with {page, x0, y0, x1, y1} or None if no bounding regions
    """
    all_bboxes = []

    for para in section.paragraphs:
        bounding_regions = para.get("bounding_regions", [])

        for br in bounding_regions:
            polygon = br.get("polygon", [])
            page_num = br.get("page_number")

            if len(polygon) == 8 and page_num:
                # Convert polygon to bbox
                bbox = self._polygon_to_bbox(polygon)
                bbox["page"] = page_num
                all_bboxes.append(bbox)

    if not all_bboxes:
        return None

    # Merge all bboxes (use first page if multi-page section)
    primary_page = section.page_range[0]
    page_bboxes = [b for b in all_bboxes if b["page"] == primary_page]

    if not page_bboxes:
        return None

    # Calculate bounding box covering all paragraphs
    return {
        "page": primary_page,
        "x0": min(b["x0"] for b in page_bboxes),
        "y0": min(b["y0"] for b in page_bboxes),
        "x1": max(b["x1"] for b in page_bboxes),
        "y1": max(b["y1"] for b in page_bboxes)
    }

def _polygon_to_bbox(self, polygon: List[float]) -> Dict:
    """Convert 8-point polygon to rectangular bbox."""
    x_coords = [polygon[i] for i in range(0, 8, 2)]
    y_coords = [polygon[i] for i in range(1, 8, 2)]

    return {
        "x0": min(x_coords),
        "y0": min(y_coords),
        "x1": max(x_coords),
        "y1": max(y_coords)
    }
```

#### C. Add bbox to table chunks in `_create_table_chunks()` (lines 512-593)

```python
def _create_table_chunks(
    self,
    enhanced_pages: List[Dict],
    narrative_chunks: List[Chunk]
) -> List[Chunk]:
    """Create separate chunks for tables."""

    for page in enhanced_pages:
        page_num = page["page_number"]
        tables = page.get("tables", [])

        for table_data in tables:
            # ... existing code ...

            builder = ChunkMetadataBuilder()
            builder.set_section_id(f"table_{table_counter}")
            builder.set_table_metadata(
                context=table_context,
                row_count=table_data.get("row_count"),
                column_count=table_data.get("column_count")
            )

            # NEW: Add table bounding box if available
            table_bbox = self._extract_table_bbox(table_data)
            if table_bbox:
                builder.set_bbox(
                    page=page_num,
                    x0=table_bbox["x0"],
                    y0=table_bbox["y0"],
                    x1=table_bbox["x1"],
                    y1=table_bbox["y1"]
                )

            # ... rest of existing code ...
```

#### D. Add helper method `_extract_table_bbox()` (NEW)

```python
def _extract_table_bbox(self, table_data: Dict) -> Optional[Dict]:
    """
    Extract bounding box from table data.

    Note: Parser currently doesn't store table bounding_regions in enhanced_pages.
    This is a placeholder for when table polygons are added to the pipeline.

    Returns:
        Dict with {x0, y0, x1, y1} or None
    """
    # TODO: Parser needs to include table bounding_regions in table_data
    # For now, return None (tables won't have bbox highlighting)
    return None
```

**Effort Estimate**: 2-3 hours
**Risk**: Low - Non-breaking change, existing chunks won't be affected

---

### Phase 2: Backend - Add Table Bounding Regions to Parser (Optional)

**Goal**: Extend parser to include table bounding regions in enhanced_pages

**Current State**: Parser extracts table page_number but not polygon coordinates
**Target State**: Parser includes full bounding_regions for tables

**Files to Modify**:
1. `backend/app/services/parsers/azure_document_intelligence_parser.py` (~50 lines)

**Changes**:

In `_extract_tables()` method (around line 574):
```python
# Current code extracts table metadata
page_num = table.bounding_regions[0].page_number

# NEW: Also extract bounding regions
table_bounding_regions = []
for br in getattr(table, "bounding_regions", []) or []:
    if br:
        table_bounding_regions.append({
            "page_number": getattr(br, "page_number", None),
            "polygon": getattr(br, "polygon", [])
        })

# Add to page_tables structure
page_tables[page_num].append({
    "table_id": table_id,
    "text": table_text,
    "row_count": row_count,
    "column_count": column_count,
    "page_number": page_num,
    "bounding_regions": table_bounding_regions  # NEW
})
```

**Effort Estimate**: 1-2 hours
**Risk**: Low - Additive change only

---

### Phase 3: Frontend - PDF Highlighting Overlay ⭐ HIGH PRIORITY

**Goal**: Render visual highlights on PDF when citation is clicked

**Files to Modify**:
1. `frontend/src/components/pdf/PDFViewer.jsx` (~150 lines)
2. Create `frontend/src/components/pdf/HighlightOverlay.jsx` (~100 lines)

**Changes**:

#### A. Update PDFViewer to accept highlight data

```jsx
export default function PDFViewer({
  fileUrl,
  initialPage = 1,
  onTextSelect,
  highlightBbox = null,  // NEW: { page, x0, y0, x1, y1 }
  onHighlightClick,      // NEW: Callback when highlight is clicked
}) {
  // ... existing state ...
  const [currentHighlight, setCurrentHighlight] = useState(highlightBbox);

  // Navigate to page when highlight changes
  useEffect(() => {
    if (highlightBbox && highlightBbox.page !== pageNumber) {
      setPageNumber(highlightBbox.page);
    }
    setCurrentHighlight(highlightBbox);
  }, [highlightBbox]);

  return (
    <div className="relative">
      {/* Existing PDF rendering */}
      <Page pageNumber={pageNumber} scale={scale} />

      {/* NEW: Highlight overlay */}
      {currentHighlight && currentHighlight.page === pageNumber && (
        <HighlightOverlay
          bbox={currentHighlight}
          pageWidth={pageWidth}
          pageHeight={pageHeight}
          scale={scale}
          onClick={onHighlightClick}
        />
      )}
    </div>
  );
}
```

#### B. Create HighlightOverlay component (NEW FILE)

```jsx
/**
 * HighlightOverlay.jsx
 * Renders a semi-transparent rectangle overlay on PDF to highlight specific regions
 */

import React from 'react';

export default function HighlightOverlay({
  bbox,          // { x0, y0, x1, y1 } in inches
  pageWidth,     // PDF page width in inches
  pageHeight,    // PDF page height in inches
  scale,         // Current zoom scale
  onClick
}) {
  // Convert PDF coordinates (inches) to screen coordinates (pixels)
  const POINTS_PER_INCH = 72; // PDF standard

  const left = (bbox.x0 / pageWidth) * 100;    // % from left
  const top = (bbox.y0 / pageHeight) * 100;    // % from top
  const width = ((bbox.x1 - bbox.x0) / pageWidth) * 100;   // % width
  const height = ((bbox.y1 - bbox.y0) / pageHeight) * 100; // % height

  return (
    <div
      className="absolute border-2 border-primary bg-primary/20 rounded cursor-pointer
                 transition-all duration-300 animate-message-glow hover:bg-primary/30"
      style={{
        left: `${left}%`,
        top: `${top}%`,
        width: `${width}%`,
        height: `${height}%`,
        pointerEvents: 'auto'
      }}
      onClick={onClick}
      title="Highlighted region"
    />
  );
}
```

#### C. Update citation click handler in parent components

Example: `frontend/src/verticals/real_estate/components/MappingDetailsDialog.jsx`

```jsx
function handleCitationClick(citation) {
  // citation now includes bbox from backend
  if (citation.bbox) {
    // Pass bbox to PDF viewer
    onCitationClick({
      page: citation.page,
      bbox: citation.bbox  // { page, x0, y0, x1, y1 }
    });
  } else {
    // Fallback to page-only navigation
    onCitationClick(citation.page);
  }
}
```

**Effort Estimate**: 4-5 hours
**Risk**: Medium - Requires coordinate system testing across different PDF sizes

---

### Phase 4: Testing & Refinement

**Test Cases**:

1. **Coordinate Accuracy**
   - Verify highlight aligns with actual text/table in PDF
   - Test across different PDF page sizes (Letter, A4, custom)
   - Test with scanned PDFs vs digital PDFs

2. **Multi-Page Sections**
   - Verify bbox uses first page of section
   - Test navigation from later pages

3. **Tables**
   - Verify table highlights (after parser enhancement)
   - Test with complex multi-column tables

4. **Edge Cases**
   - No bounding regions available (old documents)
   - Invalid coordinates (malformed data)
   - Zoomed in/out PDF rendering

5. **UX Flow**
   - Click citation → navigates to page
   - Highlight appears with animation
   - Click highlight → optional callback
   - Multiple citations on same page

**Effort Estimate**: 3-4 hours

---

## 4. Rollout Strategy

### Stage 1: Narrative Chunks Only (MVP)
- Implement Phases 1 + 3
- Test with key-value pairs and narrative text
- Tables fall back to page-only navigation

### Stage 2: Full Coverage
- Add Phase 2 (table bounding regions)
- Test with complex documents
- Handle edge cases

### Stage 3: Enhancements (Future)
- Multi-region highlights for continuation chunks
- Search result highlighting
- Click-to-edit from PDF highlight
- Screenshot/annotation tools

---

## 5. Complexity Assessment

### Backend Changes: 🟢 LOW-MEDIUM
- Polygon-to-bbox conversion: Simple math
- Chunker modification: Well-defined insertion point
- Database: Already supports bbox storage
- No breaking changes

### Frontend Changes: 🟡 MEDIUM
- Coordinate transformation: Requires careful calculation
- Overlay rendering: Standard CSS absolute positioning
- React-pdf integration: Well-documented API
- Animation/UX polish: Additional effort

### Overall Complexity: 🟡 MODERATE
**Total Effort**: 10-14 hours (2 days)
**Risk Level**: Low-Medium
**Value**: High - Significantly improves UX

---

## 6. Alternative Approaches Considered

### Option A: Store Full Polygons (Rejected)
- **Pro**: Maximum precision for non-rectangular regions
- **Con**: 4x storage size, complex rendering
- **Decision**: Rectangular bbox sufficient for 99% of cases

### Option B: Calculate on Frontend from Raw Data (Rejected)
- **Pro**: No backend changes needed
- **Con**: Requires shipping raw polygon data, increases payload size
- **Decision**: Pre-calculate and store bbox in DB for efficiency

### Option C: PDF.js TextLayer Search (Rejected)
- **Pro**: No coordinate storage needed
- **Con**: Unreliable for tables, slow for large documents, requires exact text match
- **Decision**: Explicit coordinates more reliable

---

## 7. Success Metrics

**Qualitative**:
- Users can quickly verify extracted data without manual searching
- Reduced time to review template fills
- Fewer missed errors due to improved navigation

**Quantitative** (Future Analytics):
- % of citations with bbox data (target: >90%)
- Average time from citation click to verification (target: <2 seconds)
- Highlight accuracy rate (manual spot-checking)

---

## 8. Next Steps

**Decision Required**:
1. **Approve this plan** - Proceed with implementation
2. **Simplify scope** - Start with narrative only, defer tables
3. **Defer feature** - Too complex for current sprint

**If Approved**:
1. Start with Phase 1 (backend bbox capture) - Low risk, high value
2. Test with existing documents - Verify accuracy
3. Implement Phase 3 (frontend) - Iterate on UX
4. Add Phase 2 (tables) as follow-up

---

## 9. Files Reference

**Backend Files to Modify**:
```
backend/
├── app/services/
│   ├── chunkers/
│   │   └── azure_smart_chunker.py          [~100 lines added]
│   └── parsers/
│       └── azure_document_intelligence_parser.py  [~50 lines added]
```

**Frontend Files to Modify**:
```
frontend/
└── src/components/pdf/
    ├── PDFViewer.jsx                        [~50 lines modified]
    └── HighlightOverlay.jsx                 [~100 lines NEW FILE]
```

**Database**: No schema changes - using existing JSONB storage

---

## 10. Conclusion

The PDF highlighting feature is **highly feasible** with ~70% of infrastructure already in place. The main work involves:

1. **Backend**: Extract and store bounding regions (~150 lines)
2. **Frontend**: Render highlight overlays (~150 lines)

**Total Effort**: 10-14 hours
**Value**: High - Major UX improvement for data verification
**Risk**: Low-Medium - Well-defined scope, non-breaking changes

**Recommendation**: ✅ **Proceed with implementation starting with Phase 1**
