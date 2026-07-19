"""Post-ranking renderers do not invoke upstream systems."""

import socket

from test_feasibility_presentation import _annotation, _observation, _row
from targetintel.hypothesis_cards import make_target_card


def test_feasibility_card_decoration_uses_only_constructed_annotation(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("upstream system invoked")

    import targetintel.feature_table as feature_table
    import targetintel.intent_ranking as intent_ranking
    import targetintel.role_classifier as role_classifier
    import targetintel.scoring as scoring
    import targetintel.feasibility.profiles as profiles

    monkeypatch.setattr(feature_table, "build_feature_table", forbidden)
    monkeypatch.setattr(intent_ranking, "build_intent_rankings", forbidden)
    monkeypatch.setattr(role_classifier, "classify_gene", forbidden)
    monkeypatch.setattr(scoring, "score_all_profiles", forbidden)
    monkeypatch.setattr(profiles, "build_target_feasibility_profile", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    annotation = _annotation("antibody", (_observation("tractability", "antibody"),))
    rendered = make_target_card(_row(), feasibility_annotations=(annotation,), feasibility_target_identifier_type="gene_symbol")
    assert "Target feasibility — research-only" in rendered
