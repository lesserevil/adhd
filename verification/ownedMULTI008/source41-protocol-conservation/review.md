# Source41 protocol conservation

Read-only comparison of the published profile2.1 snapshots with actual source41
cache17 CLI output, joined to compiled admission B62 and the complete core wire8
report. This adds no runtime invocation or broad qualification gate.

Only these five paths per document permit ordering changes:

- JSON Schema: `/$defs/ArchiveQuery/required`, `/$defs/FeedbackAttempt/required`,
  `/$defs/FeedbackAttemptSummary/required`, `/$defs/OptimizationProposal/required`,
  `/$defs/ReplayQuery/required`.
- OpenAPI: `/components/schemas/ArchiveQuery/required`,
  `/components/schemas/FeedbackAttempt/required`,
  `/components/schemas/FeedbackAttemptSummary/required`,
  `/components/schemas/OptimizationProposal/required`,
  `/components/schemas/ReplayQuery/required`.

The JSON record retains each original and actual array, proves unique string
membership equal, and requires every other array and typed JSON value exact.
Object key serialization order is ignored; no recursive array sorting is used.
Comparator checks deny reordered enums, examples and an unlisted array, and deny
boolean/integer substitution. Raw byte hashes remain different and explicit.
The wire report's schema digest is independently reproduced using its authored
compact/sorted-object-key JSON convention. Published files are not rewritten.

The initial link check against this isolated branch alone found root-imported
proofs absent from that checkout. Rechecking all 147 guide links against the
actual integration root plus new branch files passed. This is a checkout scope
observation, not a missing integration artifact or documentation validation claim.
No CLI marker, receipt, source, schema or runtime was changed.
