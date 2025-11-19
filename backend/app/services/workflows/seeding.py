"""Workflow template seeding on application startup.

Idempotent: only creates templates if they do not already exist by name.
"""
from sqlalchemy.orm import Session
from app.repositories.workflow_repository import WorkflowRepository
from app.services.workflows.templates import TEMPLATES as SEED_SET  # registry list


def seed_workflows(db: Session):
    repo = WorkflowRepository(db)
    existing = {w.name for w in repo.list_workflows(active_only=False)}
    created = []
    for cfg in SEED_SET:
        if cfg["name"] in existing:
            continue
        wf = repo.create_workflow(
            name=cfg["name"],
            prompt_template=cfg["prompt_template"],
            user_prompt_template=cfg.get("user_prompt_template"),  # Optional: simplified prompt for UI
            user_prompt_max_length=cfg.get("user_prompt_max_length"),  # Optional: character limit
            category=cfg["category"],
            variables_schema=cfg["variables_schema"],
            output_format=cfg["output_format"],
            min_documents=cfg["min_documents"],
            max_documents=cfg["max_documents"],
            version=cfg["version"],
            description=cfg["description"],
        )
        created.append(wf.name)
    return created
