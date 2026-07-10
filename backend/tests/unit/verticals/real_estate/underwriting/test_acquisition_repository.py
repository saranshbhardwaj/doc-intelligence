from app.db_models_documents import Document
from app.repositories.re_acquisition_repository import AcquisitionCandidateRepository


def _document(db_session, *, user_id="user-1", org_id="org-1", filename="test.pdf", content_hash="hash-1", status="completed", chunk_count=3):
    doc = Document(
        user_id=user_id,
        org_id=org_id,
        filename=filename,
        file_path=f"/tmp/{filename}",
        file_size_bytes=1024,
        content_hash=content_hash,
        page_count=10,
        status=status,
        chunk_count=chunk_count,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return doc


def test_create_and_list_candidates_scoped_to_user(db_session):
    repo = AcquisitionCandidateRepository(db_session)

    candidate = repo.create(
        user_id="user-1",
        org_id="org-1",
        payload={
            "name": "Tulsa Deal 169",
            "address": "1540 North Yale Avenue",
            "asset_class": "self_storage",
            "asset_class_confidence": 0.92,
            "source_type": "gmail",
            "source_name": "Broker email",
            "status": "needs_docs",
            "priority": "high",
            "facts": {"price": 2500000},
            "evidence": [{"label": "Self-storage language"}],
            "missing_items": ["rent_roll", "t12"],
        },
    )
    repo.create(user_id="user-2", org_id="org-1", payload={"name": "Other User Deal"})

    assert candidate.id
    assert candidate.name == "Tulsa Deal 169"
    assert candidate.facts["price"] == 2500000

    rows = repo.list(user_id="user-1")
    assert [row.name for row in rows] == ["Tulsa Deal 169"]


def test_attach_document_replaces_existing_active_slot(db_session):
    repo = AcquisitionCandidateRepository(db_session)
    candidate = repo.create(
        user_id="user-1",
        org_id="org-1",
        payload={"name": "Tulsa Deal 169", "missing_items": ["om", "rent_roll"]},
    )
    old_om = _document(db_session, content_hash="old-om", filename="old-om.pdf")
    new_om = _document(db_session, content_hash="new-om", filename="new-om.pdf")

    first_link = repo.attach_document(candidate.id, "user-1", old_om.id, "om")
    second_link = repo.attach_document(candidate.id, "user-1", new_om.id, "om")

    db_session.refresh(first_link)
    assert first_link.status == "detached"
    assert second_link.status == "attached"
    assert second_link.document_id == new_om.id

    hydrated = repo.get(candidate.id, "user-1")
    active_oms = [doc for doc in hydrated.documents if doc.doc_type == "om" and doc.status == "attached"]
    assert len(active_oms) == 1
    assert active_oms[0].document_id == new_om.id
    assert hydrated.missing_items == ["rent_roll"]


def test_attach_document_rejects_cross_user_candidate(db_session):
    repo = AcquisitionCandidateRepository(db_session)
    candidate = repo.create(user_id="user-1", org_id="org-1", payload={"name": "Tulsa Deal 169"})
    doc = _document(db_session, content_hash="om", filename="om.pdf")

    result = repo.attach_document(candidate.id, "user-2", doc.id, "om")

    assert result is None


def test_detach_document_marks_active_link_detached(db_session):
    repo = AcquisitionCandidateRepository(db_session)
    candidate = repo.create(user_id="user-1", org_id="org-1", payload={"name": "Tulsa Deal 169"})
    doc = _document(db_session, content_hash="rr", filename="rent-roll.xlsx")
    repo.attach_document(candidate.id, "user-1", doc.id, "rent_roll")

    assert repo.detach_document(candidate.id, "user-1", doc.id) is True

    hydrated = repo.get(candidate.id, "user-1")
    assert hydrated.documents[0].status == "detached"