import importlib.util
from pathlib import Path

import pytest

from app.db_models_templates import TemplateFillRun
from app.db_models_workflows import WorkflowRun


def _load_task_management_module():
    module_path = Path(__file__).resolve().parents[4] / "app" / "api" / "admin" / "task_management.py"
    spec = importlib.util.spec_from_file_location("_task_management_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeQuery:
    def __init__(self, session, args):
        self.session = session
        self.args = args
        self.filters = []

    def group_by(self, *_args):
        return self

    def all(self):
        return []

    def filter(self, *criteria):
        self.filters.extend(criteria)
        if self.args == (TemplateFillRun,):
            self.session.template_stuck_filters.extend(criteria)
        elif self.args == (WorkflowRun,):
            self.session.workflow_stuck_filters.extend(criteria)
        return self

    def count(self):
        return 0


class _FakeSession:
    def __init__(self):
        self.template_stuck_filters = []
        self.workflow_stuck_filters = []

    def query(self, *args):
        return _FakeQuery(self, args)


def _in_filter_values(filters):
    values = []
    for criterion in filters:
        bound_value = getattr(getattr(criterion, "right", None), "value", None)
        if isinstance(bound_value, list):
            values.append(set(bound_value))
    return values


@pytest.mark.asyncio
async def test_task_statistics_counts_stuck_template_fills_using_processing_statuses():
    db = _FakeSession()
    task_management = _load_task_management_module()

    await task_management.get_task_statistics(db)

    template_in_values = _in_filter_values(db.template_stuck_filters)
    assert set(TemplateFillRun.PROCESSING_STATUSES) in template_in_values
    assert {"queued", "running"} not in template_in_values
