"""Workflow template registry for domain-based template discovery.

Maps (domain, name) -> template configuration.
"""
from typing import Dict, List, Optional, Tuple
from app.utils.logging import logger


class WorkflowRegistry:
    """Registry for workflow templates across all domains."""

    def __init__(self):
        self._templates: Dict[Tuple[str, str], dict] = {}  # (domain, name) -> template
        self._by_domain: Dict[str, List[dict]] = {}  # domain -> [templates]

    def register(self, template: dict) -> None:
        """Register a workflow template.

        Args:
            template: Template dict with keys: name, domain, prompt_template, etc.
        """
        domain = template.get("domain", "private_equity")
        name = template["name"]
        key = (domain, name)

        if key in self._templates:
            logger.warning(f"Overwriting existing template: {domain}/{name}")

        self._templates[key] = template

        # Update domain index
        if domain not in self._by_domain:
            self._by_domain[domain] = []

        # Remove old version if exists
        self._by_domain[domain] = [t for t in self._by_domain[domain] if t["name"] != name]
        self._by_domain[domain].append(template)

        logger.debug(f"Registered workflow template: {domain}/{name}")

    def register_all(self, templates: List[dict]) -> None:
        """Register multiple templates.

        Args:
            templates: List of template dicts
        """
        for template in templates:
            self.register(template)

    def get(self, domain: str, name: str) -> Optional[dict]:
        """Get a template by domain and name.

        Args:
            domain: Workflow domain (private_equity, real_estate)
            name: Workflow name

        Returns:
            Template dict or None if not found
        """
        return self._templates.get((domain, name))

    def list_by_domain(self, domain: str) -> List[dict]:
        """List all templates for a domain.

        Args:
            domain: Workflow domain (private_equity, real_estate)

        Returns:
            List of template dicts
        """
        return self._by_domain.get(domain, [])

    def list_all(self) -> List[dict]:
        """List all registered templates across all domains.

        Returns:
            List of all template dicts
        """
        return list(self._templates.values())

    def get_domains(self) -> List[str]:
        """Get list of all registered domains.

        Returns:
            List of domain strings
        """
        return list(self._by_domain.keys())


# Global registry instance
_registry = WorkflowRegistry()


def get_registry() -> WorkflowRegistry:
    """Get the global workflow registry instance.

    Returns:
        WorkflowRegistry singleton
    """
    return _registry


def initialize_registry() -> None:
    """Initialize the global registry with all templates.

    Should be called once at application startup.
    """
    # Import templates from all domains
    from app.verticals.private_equity.workflows import TEMPLATES as PE_TEMPLATES
    try:
        from app.verticals.real_estate.workflows import TEMPLATES as RE_TEMPLATES
    except Exception:
        RE_TEMPLATES = []

    registry = get_registry()

    # Register PE templates
    for template in PE_TEMPLATES:
        if "domain" not in template:
            template["domain"] = "private_equity"
        registry.register(template)

    # Register RE templates
    for template in RE_TEMPLATES:
        if "domain" not in template:
            template["domain"] = "real_estate"
        registry.register(template)

    logger.info(
        f"Workflow registry initialized: "
        f"{len(PE_TEMPLATES)} PE templates, "
        f"{len(RE_TEMPLATES)} RE templates"
    )


__all__ = [
    "WorkflowRegistry",
    "get_registry",
    "initialize_registry",
]
