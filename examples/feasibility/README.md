# v0.4.0 offline feasibility demo

Run from the repository root:

```bash
python examples/feasibility/run_v040_mock_demo.py --output-dir /tmp/targetintel-v040-demo
```

This deterministic, fixture-only demonstration composes the approved public APIs: Issue 401 `TargetFeasibilityRequest` and profile contracts; Issue 402 `OpenTargetsFetchRequest`, query plans, injected `FakeOpenTargetsTransport`, resolutions, records, fetch result, cache identity, and coverage report; Issue 403 `build_target_feasibility_profile`; Issue 404 `compose_modality_with_feasibility`; and Issue 405 canonical card/HTML renderers plus their feasibility section. Its existing-style ranked row supplies score, score components, role, intent labels/scores, ranks, ordering, selection, feature values, rationale, and evidence.

The association-ranked fixture returns BRAF and CD274 only. The independently directed universe requests TAP1, IFNGR1, STAT1, NOREC, UNRES, and FAIL, so TAP1/IFNGR1/STAT1 are recovered despite being absent from the ranked fixture. Every directed request is retained in a terminal category; a separate explicit Ensembl fixture demonstrates the source contract's no-record state.

Artifacts are `demo_manifest.json`, `demo_summary.json`, `coverage_summary.json`, `protected_invariants.json`, `cards/TAP1.md`, and `reports/TAP1.html`. They retain release/query/universe/fetch/coverage/profile/modality/presentation identities and content hashes. Paths and timestamps are excluded from scientific identities.

Safety states remain descriptive: TAP1 has a source-linked observation, IFNGR1 has insufficient safety data, and STAT1 has no signal in successfully retrieved records. None means safe. TAP1 also retains conflicting tractability observations and their source identities without selecting a winner or averaging.

Antibody, small molecule, and PROTAC annotations are explicit, unranked compositions of the canonical legacy modality assessment. PROTAC is not inferred from small-molecule evidence. Feasibility is appended after ranking to canonical Markdown and HTML outputs; protected pre-existing scores, roles, ranks, ordering, selection, and feature values are asserted unchanged.

The demo is research-only and does not validate biology or clinical utility, create a feasibility score, recommend a modality, make a go/no-go decision, or measure live Open Targets coverage. It makes no HTTP request, API-key lookup, LLM/model/GPU invocation, database connection, or dependency installation.
