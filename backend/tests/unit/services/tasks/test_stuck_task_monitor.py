import importlib.util
from datetime import datetime, timezone
from pathlib import Path

from app.db_models_templates import TemplateFillRun


def _load_stuck_task_monitor_module():
    module_path = Path(__file__).resolve().parents[4] / "app" / "services" / "tasks" / "stuck_task_monitor.py"
    spec = importlib.util.spec_from_file_location("_stuck_task_monitor_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _FakeQuery:
    def __init__(self, session, args):
        self.session = session
        self.args = args

    def filter(self, *criteria):
        if self.args == (TemplateFillRun,):
            self.session.template_stuck_filters.extend(criteria)
        return self

    def all(self):
        return []


class _FakeSession:
    def __init__(self):
        self.template_stuck_filters = []

    def query(self, *args):
        return _FakeQuery(self, args)


def _in_filter_values(filters):
    values = []
    for criterion in filters:
        bound_value = getattr(getattr(criterion, "right", None), "value", None)
        if isinstance(bound_value, list):
            values.append(set(bound_value))
    return values


def test_stuck_template_fill_cleanup_uses_processing_statuses():
    db = _FakeSession()
    stuck_task_monitor = _load_stuck_task_monitor_module()

    stuck_task_monitor._cleanup_stuck_template_fills(db, datetime.now(timezone.utc))

    template_in_values = _in_filter_values(db.template_stuck_filters)
    assert set(TemplateFillRun.PROCESSING_STATUSES) in template_in_values
    assert {"queued", "running"} not in template_in_values
