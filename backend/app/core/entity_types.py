"""
Entity type constants and utilities for polymorphic job handling.

Maps entity types to their corresponding response field names and repositories.
"""
from typing import Tuple, Optional

# Mapping of entity_type to the field name used in SSE complete events
ENTITY_RESPONSE_FIELD_NAMES = {
    "extraction": "extraction_id",
    "workflow_run": "run_id",
    "template_fill_run": "fill_run_id",
    "document": "document_id",
    "analysis_run": "analysis_run_id",
    "investigation_run": "investigation_run_id",
}


def resolve_entity_owner(entity_type: str, entity_id: str, org_id: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolve the owner and org of a job entity.

    Returns:
        (owner_id, entity_org_id) tuple

    Raises:
        HTTPException 404 if entity not found or entity_type is unknown
    """
    from fastapi import HTTPException

    if entity_type == "extraction":
        from app.repositories.extraction_repository import ExtractionRepository
        extraction = ExtractionRepository().get_extraction(entity_id)
        if not extraction:
            raise HTTPException(status_code=404, detail="Extraction not found")
        return extraction.user_id, getattr(extraction, "org_id", None)

    elif entity_type == "workflow_run":
        from app.repositories.workflow_repository import WorkflowRepository
        run = WorkflowRepository.get_run_by_id(entity_id)
        if not run:
            raise HTTPException(status_code=404, detail="Workflow run not found")
        return run.user_id, getattr(run, "org_id", None)

    elif entity_type == "document":
        from app.repositories.document_repository import DocumentRepository
        doc = DocumentRepository().get_by_id(entity_id, org_id)
        if not doc:
            raise HTTPException(status_code=404, detail="Document not found")
        return doc.user_id, getattr(doc, "org_id", None)

    elif entity_type == "template_fill_run":
        from app.repositories.template_repository import TemplateRepository
        fill_run = TemplateRepository.get_fill_run_by_id(entity_id)
        if not fill_run:
            raise HTTPException(status_code=404, detail="Template fill run not found")
        return fill_run.user_id, getattr(fill_run, "org_id", None)

    elif entity_type == "analysis_run":
        from app.verticals.private_equity.diligence.repository import PEDiligenceRepository
        run = PEDiligenceRepository.get_analysis_run_by_id(entity_id)
        if not run:
            raise HTTPException(status_code=404, detail="Analysis run not found")
        return run.user_id, run.org_id

    elif entity_type == "investigation_run":
        from app.verticals.private_equity.diligence.repository import PEDiligenceRepository
        run = PEDiligenceRepository.get_investigation_run_by_id(entity_id)
        if not run:
            raise HTTPException(status_code=404, detail="Investigation run not found")
        return run.user_id, run.org_id

    else:
        raise HTTPException(status_code=404, detail=f"Unknown job entity type: {entity_type}")


def build_entity_complete_event(job) -> dict:
    """
    Build the complete event data for a job based on its entity_type.

    Args:
        job: JobState object with entity_type and entity_id

    Returns:
        Dictionary with message and appropriate entity ID field
    """
    complete_data = {"message": job.message or "Job completed successfully"}

    field_name = ENTITY_RESPONSE_FIELD_NAMES.get(job.entity_type)
    if field_name:
        complete_data[field_name] = job.entity_id

    return complete_data
