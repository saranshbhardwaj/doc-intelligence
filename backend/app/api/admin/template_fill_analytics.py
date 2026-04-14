"""Admin endpoint: template fill analytics for improvement loop."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.db_models_templates import FillRunData, TemplateFillRun
from app.services.template_fill_analytics_service import aggregate_field_stats
from app.utils.logging import logger

router = APIRouter()


@router.get("/template-fill-analytics")
def get_template_fill_analytics(
    _: None = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """
    Aggregate template fill correction stats across all completed fill runs.

    Returns per-field breakdown: how often LLM succeeded vs was corrected
    vs missed entirely (user filled from PDF or typed manually).

    Used by the operator to identify which YAML fields need synonym improvements
    or prompt fixes.
    """
    rows = (
        db.query(FillRunData)
        .join(TemplateFillRun, TemplateFillRun.id == FillRunData.fill_run_id)
        .filter(TemplateFillRun.status == "completed")
        .all()
    )

    all_extracted = [row.extracted_data for row in rows if row.extracted_data]
    field_stats = aggregate_field_stats(all_extracted)

    fields_list = sorted(field_stats.values(), key=lambda x: x["total_runs"], reverse=True)

    total_runs = len(rows)
    avg_corrected = (
        sum(f["llm_corrected"] for f in fields_list) / total_runs if total_runs else 0
    )
    avg_filled_blank = (
        sum(f["blank_filled_from_pdf"] + f["blank_filled_manually"] for f in fields_list)
        / total_runs if total_runs else 0
    )

    logger.info(
        "Template fill analytics query",
        extra={"total_runs": total_runs, "field_count": len(fields_list)},
    )

    return {
        "summary": {
            "total_runs": total_runs,
            "avg_corrected_per_run": round(avg_corrected, 2),
            "avg_filled_blank_per_run": round(avg_filled_blank, 2),
        },
        "fields": fields_list,
    }
