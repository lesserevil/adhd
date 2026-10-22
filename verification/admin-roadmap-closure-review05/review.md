# Admin roadmap leaf closure proposal

All13 explicit MULTI-006/KAFKA-006 leaves are now supported for closure. No roadmap checkbox or parent status was changed. The machine-readable map retains exact before/after checkbox text and current evidence bindings.

| Item / current line | Leaf | Current qualifying evidence |
| --- | --- | --- |
| MULTI-006 / 861 | Project lifecycle/access/catalog | nativeUI9/86 + imageUI9/86 |
| MULTI-006 / 862 | Server/project settings and inheritance | nativeUI9/86 + imageUI9/86; sourceC native core hot/backend cases |
| MULTI-006 / 863 | Context/revocation/secrets/CSRF/concurrent edits | nativeUI9/86 + imageUI9/86 |
| MULTI-006 / 864 | First proposed OIDC connection test | nativeUI9/86 + imageUI9/86 |
| MULTI-006 / 865 | Stale401 replacement-session fence | nativeUI9/86 + imageUI9/86 |
| MULTI-006 / 866 | 390px full Event IDs | nativeUI9/86 + imageUI9/86 |
| MULTI-006 / 868 | Every-role desktop/mobile interactions | nativeUI9/86 + imageUI9/86 |
| KAFKA-006 / 1005 | Raw/filtered edit/pause/backlog forms | nativeUI9/86 + imageUI9/86; current Kafka admin, caps, fairness, optional-filter |
| KAFKA-006 / 1006 | Hot connection/credentials/policy/exact replay targets | nativeUI9/86 + imageUI9/86; current Kafka policy, cutover, cutover-decision, cutover-project; actual secured Kind7/51 |
| KAFKA-006 / 1007 | Interrupted transition and quarantine repair | nativeUI9/86 + imageUI9/86; current Kafka controls, cutover-decision, cutover-project |
| KAFKA-006 / 1008 | Authorized backlog/lag/gaps/budgets/redaction | nativeUI9/86 + imageUI9/86; current Kafka controls, caps, retention, outage |
| KAFKA-006 / 1010 | Role-scoped live model/revision interactions | nativeUI9/86 + imageUI9/86; current Kafka admin, caps |
| KAFKA-006 / 1011 | Live credential/connection/filter changes | nativeUI9/86 + imageUI9/86; current Kafka cutover, policy, controls, optional-filter; actual secured Kind7/51 |

Proposed leaf-only checkbox ranges at this snapshot: MULTI-006 lines861–866 and868; KAFKA-006 lines1005–1008 and1010–1011. Apply by exact text because concurrent root edits can move line numbers.

Keep MULTI-006 and KAFKA-006 parent checkboxes unchanged. Their dependency items and remaining overall core/recovery/CNI/documentation/lifecycle gates are independently controlled. Completion of these Admin leaves does not close those gates.

The earlier review added an unnecessary requirement to duplicate secured rotation on Compose and Kind. The actual leaf does not require both security platforms: current Kind51, Kafka68 and both UI runtimes prove the specified properties. Preserve actual Kind scope, licensing and telemetry limits.

Historical false aggregates remain false. The original untraced401 is still not definitively attributed; the independently reproduced session race is repaired and qualified. Visual inspection covers specific retained samples, not every capture.

See [review.json](review.json) for all13 exact requirement texts, proposed checkbox replacements, exact case names, report hashes and dependency IDs. No new tests, runtimes, provider calls, plans or application changes were made.
