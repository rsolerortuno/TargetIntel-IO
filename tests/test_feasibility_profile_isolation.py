"""Fail-fast runtime isolation checks for Issue 403 profile construction."""

from __future__ import annotations

import socket
import subprocess

from targetintel.feasibility import build_target_feasibility_profile
from test_feasibility_profiles import request, result


def test_profile_builder_does_not_invoke_pipeline_transport_cache_or_llm(monkeypatch) -> None:
    """A validated result is normalized without touching any isolated system."""
    import targetintel.feature_table as feature_table
    import targetintel.intent_ranking as intent_ranking
    import targetintel.llm.execution as llm_execution
    import targetintel.modality as modality
    import targetintel.role_classifier as role_classifier
    import targetintel.scoring as scoring
    from targetintel.evidence import models as evidence_models
    from targetintel.feasibility import opentargets_cache, opentargets_ingestion

    fetched = result(fields={"safetyLiabilities": []})

    def forbidden(*args, **kwargs):
        raise AssertionError("profile construction invoked an isolated system")

    monkeypatch.setattr(scoring, "score_all_profiles", forbidden)
    monkeypatch.setattr(intent_ranking, "add_intent_ranks", forbidden)
    monkeypatch.setattr(role_classifier, "classify_gene", forbidden)
    monkeypatch.setattr(modality, "assign_modality_fit", forbidden)
    monkeypatch.setattr(feature_table, "build_feature_table", forbidden)
    monkeypatch.setattr(llm_execution, "execute_request", forbidden)
    monkeypatch.setattr(evidence_models, "EvidenceItem", forbidden)
    monkeypatch.setattr(opentargets_ingestion, "fetch_opentargets", forbidden)
    monkeypatch.setattr(opentargets_cache.OpenTargetsCache, "read", forbidden)
    monkeypatch.setattr(opentargets_cache.OpenTargetsCache, "write", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)

    built = build_target_feasibility_profile(request(), fetched)
    assert built.profile is not None
