"""Workflow template seeding on application startup.

Idempotent: only creates templates if they do not already exist by (domain, name).
"""
from sqlalchemy.orm import Session
from app.repositories.workflow_repository import WorkflowRepository
from app.verticals.private_equity.workflows.core import get_registry, initialize_registry


def seed_workflows(db: Session):
    # Initialize the registry first (loads all templates)
    initialize_registry()

    repo = WorkflowRepository(db)

    # Get existing workflows as (domain, name) tuples
    existing = {(w.domain, w.name) for w in repo.list_workflows(active_only=False)}
    created = []

    # Get all templates from registry
    registry = get_registry()
    all_templates = registry.list_all()

    for cfg in all_templates:
        name = cfg["name"]
        domain = cfg.get("domain", "private_equity")
        key = (domain, name)

        # Skip if already exists
        if key in existing:
            continue

        # --- CREATE WORKFLOW ---
        wf = repo.create_workflow(
            name=cfg["name"],
            domain=domain,
            prompt_template=cfg["prompt_template"],
            user_prompt_template=cfg.get("user_prompt_template"),  # Optional: simplified prompt for UI
            user_prompt_max_length=cfg.get("user_prompt_max_length"),  # Optional: character limit
            category=cfg.get("category"),
            variables_schema=cfg.get("variables_schema", {}),
            retrieval_spec=cfg.get("retrieval_spec"),  # Optional: workflow-specific retrieval sections
            output_schema=cfg.get("output_schema"),
            output_format=cfg.get("output_format", "markdown"),
            min_documents=cfg.get("min_documents", 1),
            max_documents=cfg.get("max_documents"),
            version=cfg.get("version", 1),
            description=cfg.get("description"),
        )
        created.append(f"{domain}/{wf.name}")
    return created
