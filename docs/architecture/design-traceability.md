# Design traceability

<!-- literate-ai:authority-reviewed sha256:6985451414c97730db9ebf9cd083293ba22a84059bccc35a0e56e38ca549afe5 -->

[Project guide](../README.md) → design traceability

Behavior belongs in Component specifications; target variance belongs in Flavors;
conversion technique belongs in exact skills; execution order belongs in workflows;
model eligibility belongs in routing; validation and authorization remain framework
policy. The manifest selects the source-intelligence provider, while its local database
remains
derived evidence outside source authority. Changes should update the owning artifact,
its nearby explanation or diagram,
and an end-to-end test. Illustrations aid understanding; prose requirements and
acceptance scenarios remain normative. See the [project map](../user/project-layout.md).

The contextual evidence and adaptive retrieval direction in `PROJECT.md` maps to
INFO-002, QUERY-001, SEARCH-001 through SEARCH-003 and INDEX-001 in the
[active queue](../roadmap/active-work.md). The
[shared design](../roadmap/adaptive-retrieval.md) records the rationale and
acceptance boundaries. Named contracts under `components/hub/information/` own
context, semantic queries, retrieval and qualified declarative adaptation;
`management/oidc.md` owns optional administrator sign-in. Independent acceptance
checks are under `tests/roadmap_acceptance.py`, `tests/adaptation_acceptance.py`,
`tests/oidc_acceptance.py` and `tests/roadmap_browser.py`.
Runtime changes must update the owning Component contracts and pass their recorded
generation and independent acceptance gates before usage documentation claims them.

Fresh acceptance and implementation provenance are collected in the
[roadmap implementation review](roadmap-implementation.md).
