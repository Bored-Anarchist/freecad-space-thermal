# Project instructions

## GitHub and automated verification

Use GitHub as the project's source, work-tracking, CI and release platform, following the implementation plan. Maintain unattended automated verification with each feature; do not assign manual acceptance-test execution to the user.

## Keep improving CI feedback time

Treat test/build/CI runtime as an ongoing engineering constraint. For feature and
verification changes, inspect the latest `foundation-handoff` artifact's
`ci-performance.json`, the configured stage timings, and the GitHub job critical
path. Address avoidable regressions as part of the change. Follow the measured
improvement loop in `docs/ci-performance.md` and the implementation plan.

- Target the largest measured cost; make a specific hypothesis and retain both
  successful and unsuccessful experiment results in sanitized evidence/PR text.
- Preserve all required coverage, fixed ensembles, scaling repetitions, numerical
  criteria, Debug/Release behavior and publication checks. Do not make CI faster
  by silently deleting work, caching pass verdicts or weakening assertions.
- Compare equivalent workloads and distinguish cold/warm caches, configuration,
  compiler/generator, parallelism, setup/queue time and total runner time. Use
  matched repetitions when noise could reverse the conclusion.
- Keep `ci/ci-performance-baseline.json` tied to a passing GitHub candidate/run.
  Update it deliberately after reviewing evidence, never to conceal a regression.
  Timing warnings on shared hosted runners require investigation, not relaxed
  physics tolerances or invented performance qualification.
- Verify improvements unattended and scan exact outgoing sources, scalar timing
  summaries, metadata and GitHub prose under TST-021 before publication. Raw
  profiles, generated binaries/build trees and restricted inputs remain local.

## Privacy before any online publication

The user requires private and personal information to be removed from anything put online for this open-source project. Apply this to repository contents and history being pushed, commits and author metadata, documentation, issues, pull requests, comments, discussions, posts, screenshots, logs, test evidence, packages and release assets. A private online repository is still an upload destination subject to this rule.

- Keep personal contact details, local account names and home paths, machine/internal-network identifiers, credentials, tokens, license keys, private correspondence, customer identifiers and restricted engineering data out of online material. Use relative paths, synthetic examples and approved public identities.
- Prepare a sanitized publication copy. Preserve required original model bytes and engineering evidence in their authorized local/restricted storage; do not destroy or silently alter them to make a public example.
- Check the actual outgoing files, generated artifacts, metadata and text before upload/posting. Scan staged content and outgoing history before the first remote push; CI runs again for later changes. CI alone cannot prevent disclosure in a push that has already happened.
- Keep scan reports safe: report category and sanitized location, not the sensitive matched value. Do not upload raw restricted inputs, raw logs, document properties, source maps, debug paths or screenshots before sanitization.
- Use an explicitly approved public maintainer identity and appropriate privacy-preserving commit email. Preserve required third-party license notices and public attribution; do not expose the user's private identity through new project metadata.
- If a finding cannot be safely resolved without losing necessary content, hold the affected publication and ask a focused clarification. Never treat silence or repository privacy as permission to publish personal/private data.
- If sensitive content is already online, address affected credentials and exposed artifacts promptly. Coordinate any history rewrite or destructive cleanup explicitly; do not assume removing a current file erases earlier copies.

Record implementation details and executable acceptance in the publication-privacy section of the plan and requirement TST-021.
