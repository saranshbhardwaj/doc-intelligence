from types import SimpleNamespace

import pytest

from app.repositories.re_memo_repository import ReMemoRepository


class FakeSession:
    def __init__(self, memo=None, fail_commit=False):
        self.memo = memo
        self.fail_commit = fail_commit
        self.deleted = []
        self.committed = False
        self.rolled_back = False

    def get(self, model, object_id):
        if self.memo and self.memo.id == object_id:
            return self.memo
        return None

    def delete(self, obj):
        self.deleted.append(obj)
        self.memo = None

    def commit(self):
        if self.fail_commit:
            raise RuntimeError("db unavailable")
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def make_memo(status="complete", user_id="user-1", r2_key="memo.docx"):
    return SimpleNamespace(
        id="memo-1",
        user_id=user_id,
        status=status,
        r2_key=r2_key,
    )


def test_delete_terminal_memo_removes_row_and_returns_storage_key():
    memo = make_memo(status="complete", r2_key="re-underwriting-memos/u/r/m_v1.docx")
    session = FakeSession(memo=memo)
    repo = ReMemoRepository(session)

    result = repo.delete_terminal("memo-1", "user-1")

    assert result.deleted is True
    assert result.storage_key == "re-underwriting-memos/u/r/m_v1.docx"
    assert result.status_code is None
    assert session.deleted == [memo]
    assert session.committed is True


def test_delete_terminal_memo_rejects_active_status():
    memo = make_memo(status="pending")
    session = FakeSession(memo=memo)
    repo = ReMemoRepository(session)

    result = repo.delete_terminal("memo-1", "user-1")

    assert result.deleted is False
    assert result.status_code == 409
    assert result.error == "Memo is still generating"
    assert session.deleted == []
    assert session.committed is False


def test_delete_terminal_memo_hides_other_users_memo_as_not_found():
    memo = make_memo(status="complete", user_id="other-user")
    session = FakeSession(memo=memo)
    repo = ReMemoRepository(session)

    result = repo.delete_terminal("memo-1", "user-1")

    assert result.deleted is False
    assert result.status_code == 404
    assert result.error == "Memo not found"
    assert session.deleted == []


def test_delete_terminal_memo_rolls_back_on_db_error():
    memo = make_memo(status="failed", r2_key=None)
    session = FakeSession(memo=memo, fail_commit=True)
    repo = ReMemoRepository(session)

    with pytest.raises(RuntimeError, match="db unavailable"):
      repo.delete_terminal("memo-1", "user-1")

    assert session.rolled_back is True
