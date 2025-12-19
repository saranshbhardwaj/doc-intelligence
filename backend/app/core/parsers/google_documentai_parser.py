# backend/app/services/parsers/google_documentai_parser.py
"""Google Document AI parser for digital and scanned PDFs"""
import os
import time
import fitz  # PyMuPDF for quick page count
from typing import Optional
from google.cloud import documentai_v1 as documentai
from google.cloud import storage
from google.api_core.client_options import ClientOptions
from .base import DocumentParser, ParserOutput
from app.utils.logging import logger


class GoogleDocumentAIParser(DocumentParser):
    """Google Document AI parser for comprehensive PDF extraction
    """

    # Page limit for synchronous processing
    SYNC_PAGE_LIMIT = 15

    def __init__(
        self,
        project_id: Optional[str] = None,
        location: Optional[str] = None,
        processor_id: Optional[str] = None,
        gcs_bucket: Optional[str] = None,
        timeout_seconds: int = 300
    ):
        """Initialize Google Document AI parser

        Accepts explicit arguments OR falls back to environment variables:
            GOOGLE_CLOUD_PROJECT_ID
            DOCUMENT_AI_LOCATION (default 'us')
            DOCUMENT_AI_PROCESSOR_ID
            GCS_BUCKET_NAME (only needed for batch >15 pages)
        """
        # Fallback to environment variables if arguments not provided
        if not project_id:
            project_id = os.getenv("GOOGLE_CLOUD_PROJECT_ID") or os.getenv("google_cloud_project_id")
        if not location:
            location = os.getenv("DOCUMENT_AI_LOCATION") or os.getenv("document_ai_location") or "us"
        if not processor_id:
            processor_id = os.getenv("DOCUMENT_AI_PROCESSOR_ID") or os.getenv("document_ai_processor_id")
        if not gcs_bucket:
            gcs_bucket = os.getenv("GCS_BUCKET_NAME") or os.getenv("gcs_bucket_name")

        self.project_id = project_id
        self.location = location
        self.processor_id = processor_id
        self.gcs_bucket = gcs_bucket
        self.timeout_seconds = timeout_seconds
        self._cost_per_page = 0.0015  # Pricing: $1.50 per 1,000 pages

        # Validate required config
        if not self.project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT_ID environment variable is required")
        if not self.processor_id:
            raise ValueError("DOCUMENT_AI_PROCESSOR_ID environment variable is required")

        # Initialize client with endpoint
        opts = ClientOptions(
            api_endpoint=f"{self.location}-documentai.googleapis.com"
        )
        self.client = documentai.DocumentProcessorServiceClient(client_options=opts)

        # Build processor resource name
        self.processor_name = self.client.processor_path(
            self.project_id,
            self.location,
            self.processor_id
        )

        logger.info(
            f"GoogleDocumentAI initialized: project={self.project_id}, "
            f"location={self.location}, processor={self.processor_id}"
        )

    @property
    def name(self) -> str:
        return "google_documentai"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def cost_per_page(self) -> float:
        return self._cost_per_page

    def supports_pdf_type(self, pdf_type: str) -> bool:
        """Google Document AI supports both digital and scanned PDFs"""
        return pdf_type in ("digital", "scanned")

    async def parse(self, file_path: str, pdf_type: str) -> ParserOutput:
        """Extract text from PDF using Google Document AI

        Automatically chooses sync (<=15 pages) or batch (>15 pages) processing

        Args:
            file_path: Path to PDF file
            pdf_type: PDF type ('digital' or 'scanned')

        Returns:
            ParserOutput with extracted text and metadata
        """
        start_time = time.time()

        try:
            # Quick page count check using PyMuPDF
            doc = fitz.open(file_path)
            page_count = len(doc)
            doc.close()

            logger.info(
                f"GoogleDocumentAI: {file_path} has {page_count} pages (type: {pdf_type})"
            )

            # Choose processing method based on page count
            if page_count <= self.SYNC_PAGE_LIMIT:
                logger.info(f"Using SYNC processing (≤{self.SYNC_PAGE_LIMIT} pages)")
                return await self._parse_sync(file_path, pdf_type, page_count, start_time)
            else:
                logger.info(f"Using BATCH processing (>{self.SYNC_PAGE_LIMIT} pages)")
                return await self._parse_batch(file_path, pdf_type, page_count, start_time)

        except Exception as e:
            processing_time_ms = int((time.time() - start_time) * 1000)
            logger.error(f"GoogleDocumentAI parsing failed after {processing_time_ms}ms: {e}")
            raise RuntimeError(f"Google Document AI parsing failed: {str(e)}") from e

    async def _parse_sync(
        self, file_path: str, pdf_type: str, page_count: int, start_time: float
    ) -> ParserOutput:
        """Synchronous processing for small documents (≤15 pages)"""
        # Read PDF file
        with open(file_path, 'rb') as f:
            pdf_bytes = f.read()

        logger.info(f"Processing {len(pdf_bytes)} bytes synchronously")

        # Create the document
        raw_document = documentai.RawDocument(
            content=pdf_bytes,
            mime_type="application/pdf"
        )

        # Create the request
        request = documentai.ProcessRequest(
            name=self.processor_name,
            raw_document=raw_document
        )

        # Process the document
        result = self.client.process_document(
            request=request,
            timeout=self.timeout_seconds
        )

        document = result.document

        # Extract text
        extracted_text = document.text

        # Calculate cost
        cost = page_count * self.cost_per_page

        processing_time_ms = int((time.time() - start_time) * 1000)

        logger.info(
            f"GoogleDocumentAI (SYNC) extracted {len(extracted_text)} chars from "
            f"{page_count} pages in {processing_time_ms}ms (cost: ${cost:.4f})"
        )

        return ParserOutput(
            text=extracted_text,
            page_count=page_count,
            parser_name=self.name,
            parser_version=self.version,
            processing_time_ms=processing_time_ms,
            cost_usd=cost,
            pdf_type=pdf_type,
            metadata={
                "processing_mode": "synchronous",
                "mime_type": document.mime_type,
                "char_count": len(extracted_text),
                "project_id": self.project_id,
                "location": self.location,
                "processor_id": self.processor_id,
                "avg_chars_per_page": len(extracted_text) / page_count if page_count > 0 else 0
            }
        )

    async def _parse_batch(
        self, file_path: str, pdf_type: str, page_count: int, start_time: float
    ) -> ParserOutput:
        """Batch processing for large documents (>15 pages)"""
        import uuid
        from google.api_core import operation
        from google.api_core import retry

        if not self.gcs_bucket:
            raise ValueError(
                "Batch processing requires GCS_BUCKET_NAME environment variable. "
                "Please set it to a Google Cloud Storage bucket name."
            )

        # Generate unique job ID
        job_id = f"docai-{uuid.uuid4().hex[:8]}"
        gcs_input_uri = f"gs://{self.gcs_bucket}/input/{job_id}.pdf"
        gcs_output_uri_prefix = f"gs://{self.gcs_bucket}/output/{job_id}/"

        logger.info(f"Batch job {job_id}: Uploading to {gcs_input_uri}")

        # Upload PDF to GCS
        storage_client = storage.Client(project=self.project_id)
        bucket = storage_client.bucket(self.gcs_bucket)
        input_blob = bucket.blob(f"input/{job_id}.pdf")

        with open(file_path, 'rb') as f:
            input_blob.upload_from_file(f)

        logger.info(f"Batch job {job_id}: File uploaded, starting batch processing")

        # Create batch process request
        gcs_documents = documentai.GcsDocuments(
            documents=[
                documentai.GcsDocument(
                    gcs_uri=gcs_input_uri,
                    mime_type="application/pdf"
                )
            ]
        )

        input_config = documentai.BatchDocumentsInputConfig(
            gcs_documents=gcs_documents
        )

        output_config = documentai.DocumentOutputConfig(
            gcs_output_config=documentai.DocumentOutputConfig.GcsOutputConfig(
                gcs_uri=gcs_output_uri_prefix
            )
        )

        batch_request = documentai.BatchProcessRequest(
            name=self.processor_name,
            input_documents=input_config,
            document_output_config=output_config
        )

        # Start batch process
        operation_result = self.client.batch_process_documents(batch_request)

        logger.info(f"Batch job {job_id}: Waiting for completion...")

        # Wait for operation to complete (polling)
        operation_result.result(timeout=self.timeout_seconds)

        logger.info(f"Batch job {job_id}: Processing complete, fetching results")

        # Fetch results from GCS
        output_blobs = list(bucket.list_blobs(prefix=f"output/{job_id}/"))

        if not output_blobs:
            raise RuntimeError(f"No output files found for batch job {job_id}")

        # Process ALL JSON files and combine text
        # Document AI may output multiple JSON files for a single document
        all_text_parts = []
        json_file_count = 0

        for blob in output_blobs:
            # Skip non-JSON files
            if blob.content_type != "application/json":
                logger.debug(f"Skipping non-JSON file: {blob.name} (type: {blob.content_type})")
                continue

            json_file_count += 1
            logger.info(f"Processing JSON file {json_file_count}: {blob.name}")

            # Download and parse each JSON file
            json_bytes = blob.download_as_bytes()

            # Extract text from Document AI format
            document = documentai.Document.from_json(json_bytes, ignore_unknown_fields=True)

            if document.text:
                all_text_parts.append(document.text)
                logger.info(f"  Extracted {len(document.text)} chars from {blob.name}")

        if not all_text_parts:
            raise RuntimeError(f"No text extracted from batch job {job_id}")

        # Combine all text parts
        extracted_text = "\n\n".join(all_text_parts)

        logger.info(
            f"Batch job {job_id}: Combined {json_file_count} JSON files, "
            f"total {len(extracted_text)} characters"
        )

        # Calculate cost
        cost = page_count * self.cost_per_page

        processing_time_ms = int((time.time() - start_time) * 1000)

        logger.info(
            f"GoogleDocumentAI (BATCH) extracted {len(extracted_text)} chars from "
            f"{page_count} pages in {processing_time_ms}ms (cost: ${cost:.4f})"
        )

        # Cleanup GCS files
        try:
            input_blob.delete()
            for blob in output_blobs:
                blob.delete()
            logger.info(f"Batch job {job_id}: Cleaned up GCS files")
        except Exception as e:
            logger.warning(f"Failed to cleanup GCS files for job {job_id}: {e}")

        return ParserOutput(
            text=extracted_text,
            page_count=page_count,
            parser_name=self.name,
            parser_version=self.version,
            processing_time_ms=processing_time_ms,
            cost_usd=cost,
            pdf_type=pdf_type,
            metadata={
                "processing_mode": "batch",
                "batch_job_id": job_id,
                "json_file_count": json_file_count,
                "mime_type": "application/pdf",
                "char_count": len(extracted_text),
                "project_id": self.project_id,
                "location": self.location,
                "processor_id": self.processor_id,
                "gcs_bucket": self.gcs_bucket,
                "avg_chars_per_page": len(extracted_text) / page_count if page_count > 0 else 0
            }
        )
