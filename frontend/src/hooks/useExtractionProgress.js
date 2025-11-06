/**
 * useExtractionProgress Hook
 *
 * Manages document extraction with real-time progress tracking via SSE.
 *
 * Usage:
 * ```jsx
 * import { useAuth } from '@clerk/clerk-react';
 *
 * const { getToken } = useAuth();
 * const { upload, progress, result, error, retry, isProcessing } = useExtractionProgress(getToken);
 *
 * const handleUpload = async (file) => {
 *   await upload(file);
 * };
 * ```
 */

/**
 * useExtractionProgress Hook
 * Manages document extraction with real-time progress tracking via SSE.
 *
 * @param {Function} getToken - Clerk's getToken function from useAuth hook
 */
import { useState, useRef, useCallback } from 'react';
import { uploadDocument, streamProgress, fetchExtractionResult, retryJob } from '../services/extractionService';

export default function useExtractionProgress(getToken) {
    // State
    const [progress, setProgress] = useState(null);
    const [result, setResult] = useState(null);
    const [error, setError] = useState(null);
    const [isProcessing, setIsProcessing] = useState(false);

    // Refs
    const cleanupRef = useRef(null);
    const jobIdRef = useRef(null);
    const extractionIdRef = useRef(null);

    // Reset all state
    const reset = useCallback(() => {
        setProgress(null);
        setResult(null);
        setError(null);
        setIsProcessing(false);
        if (cleanupRef.current) {
            cleanupRef.current();
            cleanupRef.current = null;
        }
        jobIdRef.current = null;
        extractionIdRef.current = null;
    }, []);

    // Progress handler
    const handleProgress = useCallback((data) => {
        const percent = data.progress_percent ?? data.progress;
        const stage = data.current_stage ?? data.stage;
        setProgress({
            status: data.status,
            percent,
            message: data.message,
            stage,
            stages: {
                parsing: data.parsing_completed,
                chunking: data.chunking_completed,
                summarizing: data.summarizing_completed,
                extracting: data.extracting_completed
            }
        });
    }, []);

    // Complete event (marks UI complete but waits for end to fetch result)
    const handleComplete = useCallback(() => {
        setProgress({
            status: 'completed',
            percent: 100,
            message: 'Extraction completed successfully!',
            stage: 'completed',
            stages: {
                parsing: true,
                chunking: true,
                summarizing: true,
                extracting: true
            }
        });
    }, []);

    // End event triggers final result fetch if success
    const handleEnd = useCallback(async (data) => {
        if (data?.reason === 'completed') {
            try {
                const extractionResult = await fetchExtractionResult(extractionIdRef.current, getToken);
                setResult(extractionResult);
            } catch (err) {
                console.error('Failed to fetch extraction result:', err);
                setError({
                    message: 'Failed to retrieve extraction result',
                    type: 'fetch_error',
                    isRetryable: true
                });
            }
        }
        // Clear sessionStorage when extraction finishes
        sessionStorage.removeItem('active_job_id');
        sessionStorage.removeItem('active_extraction_id');
        setIsProcessing(false);
    }, [getToken]);

    // Error handler
    const handleError = useCallback((data) => {
        setError({
            message: data.error_message,
            stage: data.error_stage,
            type: data.error_type,
            isRetryable: data.is_retryable
        });
        setIsProcessing(false);
    }, []);

    // Upload and start streaming
    const upload = useCallback(async (file) => {
        reset();
        setIsProcessing(true);
        try {
            const response = await uploadDocument(file, getToken);
            console.log('📤 Upload response:', response);
            // Treat from_cache or from_history as instant result
            if (response.from_cache || response.from_history) {
                setProgress({
                    status: 'parsing',
                    percent: 20,
                    message: response.from_cache ? 'Checking cache...' : 'Checking history...',
                    stage: 'parsing',
                    stages: { parsing: false, chunking: false, summarizing: false, extracting: false }
                });
                await new Promise((resolve) => setTimeout(resolve, 600));
                setProgress({
                    status: 'extracting',
                    percent: 60,
                    message: response.from_cache ? 'Retrieving cached result...' : 'Retrieving previous result...',
                    stage: 'extracting',
                    stages: { parsing: true, chunking: true, summarizing: true, extracting: false }
                });
                await new Promise((resolve) => setTimeout(resolve, 900));
                setResult(response);
                setProgress({
                    status: 'completed',
                    percent: 100,
                    message: response.from_cache ? 'Retrieved from cache' : 'Retrieved from history',
                    stage: 'completed',
                    stages: { parsing: true, chunking: true, summarizing: true, extracting: true }
                });
                setIsProcessing(false);
                return response;
            }
            // Only run SSE/session logic if job_id is present
            if (response.job_id) {
                jobIdRef.current = response.job_id;
                extractionIdRef.current = response.extraction_id;
                sessionStorage.setItem('active_job_id', response.job_id);
                sessionStorage.setItem('active_extraction_id', response.extraction_id);
                streamProgress(response.job_id, getToken, {
                    onProgress: handleProgress,
                    onComplete: handleComplete,
                    onError: handleError,
                    onEnd: handleEnd
                }).then(cleanup => {
                    cleanupRef.current = cleanup;
                });
            }
            return response;
        } catch (err) {
            console.error('Upload failed:', err);
            let errorMessage = 'Failed to upload document';
            let errorType = 'upload_error';
            if (err.response?.status === 429) {
                errorMessage = err.response.data.detail?.message || 'Rate limit exceeded';
                errorType = 'rate_limit_error';
            } else if (err.response?.status === 401) {
                errorMessage = 'Authentication required. Please sign in.';
                errorType = 'auth_error';
            } else if (err.response?.status === 403) {
                errorMessage = err.response.data.detail?.message || 'Page limit exceeded';
                errorType = 'limit_error';
            } else if (err.response?.data?.detail) {
                errorMessage = err.response.data.detail;
            }
            setError({ message: errorMessage, type: errorType, isRetryable: errorType !== 'rate_limit_error' });
            setIsProcessing(false);
            throw err;
        }
    }, [reset, handleProgress, handleComplete, handleError, handleEnd, getToken]);

    // Retry failed job
    const retry = useCallback(async () => {
        if (!jobIdRef.current) return;
        setError(null);
        setIsProcessing(true);
        try {
            const response = await retryJob(jobIdRef.current, getToken);
            jobIdRef.current = response.job_id;

            // Start SSE stream (async to get token first)
            streamProgress(response.job_id, getToken, {
                onProgress: handleProgress,
                onComplete: handleComplete,
                onError: handleError,
                onEnd: handleEnd
            }).then(cleanup => {
                cleanupRef.current = cleanup;
            });

            return response;
        } catch (err) {
            console.error('Retry failed:', err);
            setError({ message: 'Failed to retry job', type: 'retry_error', isRetryable: false });
            setIsProcessing(false);
            throw err;
        }
    }, [handleProgress, handleComplete, handleError, handleEnd, getToken]);

    // Cancel ongoing extraction
    const cancel = useCallback(() => {
        if (cleanupRef.current) {
            cleanupRef.current();
            cleanupRef.current = null;
        }
        setIsProcessing(false);
        setProgress(null);
    }, []);

    // Reconnect to an active extraction after navigation
    const reconnect = useCallback(() => {
        const storedJobId = sessionStorage.getItem('active_job_id');
        const storedExtractionId = sessionStorage.getItem('active_extraction_id');

        if (storedJobId && storedExtractionId) {
            console.log('🔄 Reconnecting to active extraction:', storedJobId);
            jobIdRef.current = storedJobId;
            extractionIdRef.current = storedExtractionId;
            setIsProcessing(true);

            // Start SSE stream
            streamProgress(storedJobId, getToken, {
                onProgress: handleProgress,
                onComplete: handleComplete,
                onError: handleError,
                onEnd: handleEnd
            }).then(cleanup => {
                cleanupRef.current = cleanup;
            });
        }
    }, [getToken, handleProgress, handleComplete, handleError, handleEnd]);

    return {
        upload,
        retry,
        cancel,
        reset,
        reconnect,
        progress,
        result,
        error,
        isProcessing,
        jobId: jobIdRef.current,
        extractionId: extractionIdRef.current
    };
}
