from app.db_models_re import AcquisitionCandidate, AcquisitionCandidateDocument, UnderwritingRun


def test_acquisition_candidate_tables_are_registered():
    assert AcquisitionCandidate.__tablename__ == "re_acquisition_candidates"
    assert AcquisitionCandidateDocument.__tablename__ == "re_acquisition_candidate_documents"
    assert "source_metadata" in UnderwritingRun.__table__.columns