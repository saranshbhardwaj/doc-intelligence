# Frontend Progress Tracking Implementation

This document describes the frontend implementation for real-time document extraction progress tracking using Server-Sent Events (SSE).

## Architecture Overview

The frontend uses a modular architecture with three main components:

```
┌─────────────────────────────────────────┐
│         FileUploader Component          │
│  (User uploads PDF, sees progress)      │
└───────────────┬─────────────────────────┘
                │
                │ uses
                ▼
┌─────────────────────────────────────────┐
│     useExtractionProgress Hook          │
│  (Manages state & coordinates SSE)      │
└───────────────┬─────────────────────────┘
                │
                │ calls
                ▼
┌─────────────────────────────────────────┐
│      extractionService.js               │
│  (API calls, SSE connection handling)   │
└─────────────────────────────────────────┘
```

## File Structure

```
frontend/src/
├── services/
│   └── extractionService.js       # API calls and SSE streaming
├── hooks/
│   └── useExtractionProgress.js   # React hook for state management
└── components/
    └── upload/
        ├── FileUploader.jsx       # Updated uploader with progress
        ├── ProgressTracker.jsx    # Progress display component
        └── ProgressTracker.css    # Styling
```

## Implementation Details

### 1. Extraction Service (`services/extractionService.js`)

Handles all API interactions and SSE streaming:

**Functions:**
- `uploadDocument(file)` - Upload PDF to backend
- `streamProgress(jobId, callbacks)` - Stream progress via SSE
- `fetchExtractionResult(extractionId)` - Get final result
- `retryJob(jobId)` - Retry failed extraction
- `getJobStatus(jobId)` - Poll job status (fallback)

**Key Features:**
- EventSource-based SSE connection
- Automatic cleanup on completion/error
- Returns cleanup function for manual cancellation

### 2. React Hook (`hooks/useExtractionProgress.js`)

Manages extraction state and coordinates SSE updates:

**Exports:**
```javascript
{
  upload,        // Function: Upload and start tracking
  retry,         // Function: Retry failed job
  cancel,        // Function: Cancel ongoing extraction
  reset,         // Function: Reset all state
  progress,      // Object: Current progress state
  result,        // Object: Final extraction result
  error,         // Object: Error details
  isProcessing,  // Boolean: Processing status
  jobId,         // String: Current job ID
  extractionId   // String: Current extraction ID
}
```

**Progress Object Structure:**
```javascript
{
  status: "parsing" | "chunking" | "summarizing" | "extracting" | "completed",
  percent: 0-100,
  message: "User-friendly status message",
  stage: "parsing",
  stages: {
    parsing: true,
    chunking: false,
    summarizing: false,
    extracting: false
  }
}
```

**Error Object Structure:**
```javascript
{
  message: "Error description",
  stage: "parsing",
  type: "parsing_error",
  isRetryable: true
}
```

### 3. Progress Tracker Component (`ProgressTracker.jsx`)

Visual display of extraction progress:

**Features:**
- Real-time progress bar
- Stage indicators with completion status
- Current stage highlighting with spinner
- Error display with retry button
- Responsive design
- Dark mode support

**Props:**
```javascript
{
  progress: progressObject,  // Progress state
  error: errorObject,       // Error state
  onRetry: () => {}         // Retry callback
}
```

### 4. Updated FileUploader (`FileUploader.jsx`)

**Changes from Original:**
- Removed old progress tracking logic
- Integrated `useExtractionProgress` hook
- Replaced static spinner with `ProgressTracker` component
- Automatic result/error handling via useEffect
- Simplified upload logic

## Flow Diagram

### Cache Hit (Instant Result)

```
User uploads PDF
      ↓
Backend checks cache
      ↓
Cache HIT (200 OK)
      ↓
Result displayed immediately
(No SSE connection)
```

### Cache Miss (Async Processing)

```
User uploads PDF
      ↓
Backend checks cache
      ↓
Cache MISS (202 Accepted)
      ↓
Returns job_id + extraction_id
      ↓
Frontend opens SSE connection
      ↓
Backend sends progress events
      ↓
┌─────────────────────────┐
│  Parsing (5-15%)        │ ← SSE event
├─────────────────────────┤
│  Chunking (20-30%)      │ ← SSE event
├─────────────────────────┤
│  Summarizing (40-60%)   │ ← SSE event
├─────────────────────────┤
│  Extracting (70-95%)    │ ← SSE event
├─────────────────────────┤
│  Completed (100%)       │ ← SSE event
└─────────────────────────┘
      ↓
SSE connection closes
      ↓
Frontend fetches final result
      ↓
Result displayed to user
```

### Error and Retry Flow

```
Processing fails at stage X
      ↓
SSE sends error event with:
- error_stage
- error_message
- is_retryable
      ↓
User clicks "Retry"
      ↓
Frontend calls retry API
      ↓
Backend resumes from last successful stage
      ↓
New job_id returned
      ↓
SSE reconnects with new job_id
      ↓
Processing continues...
```

## Testing the Implementation

### Step 1: Run Backend Migration

```bash
cd backend
python migrate_add_job_state.py
```

This creates the `job_states` table needed for progress tracking.

### Step 2: Start Backend

```bash
cd backend
python -m uvicorn main:app --reload --port 8000
```

### Step 3: Start Frontend

```bash
cd frontend
npm run dev
```

### Step 4: Test Cache Hit

1. Upload a PDF document
2. Should see either:
   - **Cache hit**: Instant result (no progress bar)
   - **Cache miss**: Progress tracker appears

### Step 5: Test Cache Miss & Progress

1. Upload a new/unique PDF (modify the file slightly if reusing)
2. Observe progress stages:
   - Parsing PDF (5-15%)
   - Chunking Document (20-30%)
   - Summarizing Sections (40-60%)
   - Extracting Data (70-95%)
   - Completion (100%)

### Step 6: Test Error Handling

To simulate an error, you can:

1. **Stop backend mid-processing**: Upload a large PDF, then stop the backend
   - Should see connection error with retry button

2. **Invalid LLM API key**: Temporarily break the Anthropic API key in backend
   - Should see LLM error with retry button

3. **Rate limit**: Exceed rate limit
   - Should see rate limit error (not retryable)

### Step 7: Test Retry

1. Trigger an error (see Step 6)
2. Click "Retry from Last Stage"
3. Processing should resume from where it failed

## Browser Testing

### Check SSE Connection

Open browser DevTools → Network tab → Filter by "stream"

You should see:
- Request to `/api/jobs/{job_id}/stream`
- Type: `eventsource`
- Status: `200 (pending)`
- Messages streaming in

### Check Events

In the Network tab, click the SSE request → "Messages" tab

You should see events like:
```
progress: {"status": "parsing", "progress_percent": 10, ...}
progress: {"status": "chunking", "progress_percent": 25, ...}
progress: {"status": "summarizing", "progress_percent": 50, ...}
progress: {"status": "extracting", "progress_percent": 80, ...}
complete: {"status": "completed", "extraction_id": "..."}
```

## Troubleshooting

### Issue: SSE Connection Fails

**Symptoms:** No progress updates, connection error immediately

**Solutions:**
1. Check CORS configuration in backend
2. Ensure backend is running and accessible
3. Check browser console for errors
4. Verify `/api/jobs/{job_id}/stream` endpoint exists

### Issue: Progress Stuck at 0%

**Symptoms:** Progress bar doesn't move

**Solutions:**
1. Check backend logs for errors
2. Verify `JobProgressTracker` is being used in `extract.py`
3. Check database - is `job_states` table populated?
4. Verify SSE is receiving events (DevTools → Network)

### Issue: No Progress Bar Appears

**Symptoms:** Upload succeeds but no progress shown

**Solutions:**
1. This is normal for cache hits (instant results)
2. For cache miss, check that response has `job_id`
3. Verify `useExtractionProgress` hook is properly integrated
4. Check React DevTools for state updates

### Issue: Retry Doesn't Work

**Symptoms:** Retry button doesn't do anything

**Solutions:**
1. Check backend logs for retry endpoint errors
2. Verify job_id is being passed correctly
3. Check that intermediate results were saved
4. Ensure error type is marked as retryable

## Performance Considerations

### SSE Polling Interval

The backend polls the database every 2 seconds. To adjust:

**File:** `backend/app/api/jobs.py`

```python
async def stream_job_progress(job_id: str):
    # ...
    await asyncio.sleep(2)  # Change this value
```

**Trade-offs:**
- Lower interval (e.g., 1s) = More responsive, higher DB load
- Higher interval (e.g., 5s) = Less responsive, lower DB load

### Memory Management

The SSE connection is automatically cleaned up:
- On component unmount
- On completion
- On error

Manual cleanup is also available:
```javascript
const { cancel } = useExtractionProgress();
// Later...
cancel(); // Closes SSE connection
```

## Future Enhancements

### 1. WebSocket Alternative

For lower latency, consider WebSocket instead of SSE:
- Better for high-frequency updates
- Bidirectional communication
- More complex to implement

### 2. Progress Persistence

Store progress in localStorage to survive page refresh:
```javascript
useEffect(() => {
  localStorage.setItem('currentJob', JSON.stringify({ jobId, extractionId }));
}, [jobId, extractionId]);
```

### 3. Multiple Concurrent Uploads

Track multiple jobs simultaneously:
```javascript
const jobs = useMultipleExtractions(); // Future hook
jobs.forEach(job => <ProgressTracker key={job.id} {...job} />);
```

### 4. Estimated Time Remaining

Calculate ETA based on stage timing:
```javascript
const eta = calculateETA(progress.percent, startTime);
// "Estimated time remaining: 45 seconds"
```

## API Reference

### POST /api/extract

Upload a document for extraction.

**Request:**
```
Content-Type: multipart/form-data
file: <PDF file>
```

**Response (Cache Hit - 200 OK):**
```json
{
  "success": true,
  "data": { ... },
  "metadata": { ... },
  "from_cache": true
}
```

**Response (Cache Miss - 202 Accepted):**
```json
{
  "success": true,
  "job_id": "uuid",
  "extraction_id": "uuid",
  "stream_url": "/api/jobs/{job_id}/stream",
  "result_url": "/api/extractions/{extraction_id}",
  "from_cache": false
}
```

### GET /api/jobs/{job_id}/stream

Stream job progress via Server-Sent Events.

**Events:**

**progress:**
```json
{
  "status": "parsing",
  "progress_percent": 10,
  "message": "Parsing PDF...",
  "current_stage": "parsing",
  "parsing_completed": false,
  "chunking_completed": false,
  "summarizing_completed": false,
  "extracting_completed": false
}
```

**complete:**
```json
{
  "status": "completed",
  "extraction_id": "uuid"
}
```

**error:**
```json
{
  "error_stage": "parsing",
  "error_message": "Failed to parse PDF",
  "error_type": "parsing_error",
  "is_retryable": true
}
```

### GET /api/extractions/{extraction_id}

Fetch final extraction result.

**Response (200 OK):**
```json
{
  "success": true,
  "data": { ... },
  "metadata": {
    "extraction_id": "uuid",
    "filename": "document.pdf",
    "pages": 42,
    "processing_time_ms": 45000,
    "cost_usd": 0.125
  },
  "from_cache": false
}
```

### POST /api/jobs/{job_id}/retry

Retry a failed job from last successful stage.

**Response (200 OK):**
```json
{
  "success": true,
  "job_id": "new-uuid",
  "extraction_id": "same-uuid",
  "message": "Job retry initiated from stage: chunking",
  "resume_from_stage": "chunking"
}
```

## Summary

The frontend progress tracking system provides:

✅ **Real-time updates** via Server-Sent Events
✅ **Visual progress indicators** with stage breakdown
✅ **Error handling** with user-friendly messages
✅ **Retry capability** resuming from last successful stage
✅ **Cache-aware routing** (instant vs async)
✅ **Modular architecture** for easy maintenance
✅ **Dark mode support** throughout
✅ **Responsive design** for all screen sizes

The system is production-ready and can be tested end-to-end by following the steps in this guide.
