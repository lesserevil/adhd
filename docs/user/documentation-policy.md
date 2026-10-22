# Documentation consistency

[Project guide](../README.md) → documentation consistency

These rules apply to every project change, including generated implementations,
helper scripts, configuration, APIs, the web console, and deployment procedures.
Documentation review is a required completion gate for contributors and agents.

## Describe supported behavior

- Component specifications remain the authority for intended product behavior.
  User and administrator guides must describe what the current accepted
  implementation actually supports, including prerequisites and limitations.
- Check capability claims against the owning specification, current implementation,
  and relevant acceptance evidence. A specification or completed roadmap checkbox
  alone does not prove that a feature is implemented. Check claims that a feature
  is absent as carefully as claims that it exists.
- Label planned, experimental, unverified, and platform-specific behavior explicitly.
  Keep future features in the roadmap; do not present them as available instructions.
- If implementation and specification disagree, record the defect and its impact.
  Correct the owning authority or implementation through the normal lifecycle and
  document the current limitation. Do not silently weaken a requirement to make
  documentation agree or claim the feature is complete while the conflict remains.

## Update documentation with the change

- Before implementation, identify affected claims and examples across `README.md`,
  `PROJECT.md`, `docs/`, agent skills, CLI help, and UI guidance. Search for operation
  names, configuration keys, defaults, and old limitation statements as applicable.
- Update affected documentation in the same change as the behavior. Cover additions,
  removals, renamed fields, defaults, authentication and visibility rules, retry and
  persistence semantics, platform support, and upgrade or rollback requirements.
- Keep each detailed procedure or interface description in one owning document and
  link to it from summaries. Review existing summaries for contradictions whenever
  the owning document changes. Preserve historical evidence as historical evidence;
  do not rewrite old test reports to imply validation of a newer implementation.
- Verify commands, paths, flags, request/response examples, and configuration against
  the relevant helpers and interfaces. Exercise changed runnable examples in an
  isolated environment under the normal execution-authorization rules. Record an
  unavailable runtime or dependency as unverified; do not claim the example passed.
- When a behavior change needs regression coverage, include an acceptance check for
  the documented observable outcome, including relevant error or permission cases.
  Documentation-only corrections require review against existing implementation and
  evidence; they do not require regenerating the service.

## Required completion evidence

Before marking a work item complete or handing a change over for landing:

1. Record the affected documentation paths in the work item's evidence. If no
   documentation changes are needed, record the reviewed surfaces and why their
   existing descriptions remain accurate. A bare “no docs needed” is insufficient.
2. Review both supported-feature and limitation statements, cross-document
   summaries, links, and examples. Identify the owning contract and the
   implementation or acceptance evidence supporting any corrected behavior claim.
3. Run the read-only `litai project documentation-update` plan and review its
   findings against current authority and command help; record corrections or
   evidence for false positives. After the content review, use
   `litai project documentation-review --record` if its review marker is stale.
   Run `litai verify` and relevant checks for changed examples or behavior. Record
   fresh results separately from previously checked-in acceptance reports and
   identify skipped gates and checks that were not run.
4. Resolve documentation contradictions before closing the item. If supporting
   evidence is unavailable, retain the unchecked evidence task and label the claim
   unverified until it can be established.

`litai verify` checks declared project gates; a passing result does not by itself
prove that prose matches runtime behavior. The claim review above remains required.
