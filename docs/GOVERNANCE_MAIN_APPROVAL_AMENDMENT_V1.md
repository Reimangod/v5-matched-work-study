# Main branch approval-count governance amendment v1

Status: `OWNER_AUTHORIZED_REQUIRED_APPROVAL_COUNT_ZERO`

This additive record applies only to integrating the already audited stacked pull requests for the V5 matched-work infrastructure No-Go release.

Authorization basis: the repository owner explicitly waived independent human pre-review as a scientific protocol, stage-transition, and experiment-start requirement. This is a governance decision; it is not independent review, third-party approval, or scientific outcome evidence.

Before application, `main` branch protection was observed as:

- strict required status check: `release-gate`
- pull request required
- dismiss stale reviews: enabled
- require last-push approval: enabled
- required approving review count: 1
- conversation resolution: required
- admin enforcement: enabled
- force pushes: disabled
- branch deletion: disabled

Authorized change:

- set only `required_approving_review_count` from `1` to `0`

Safeguards that must remain unchanged:

- `release-gate` remains strict and required
- pull requests remain required
- stale-review dismissal remains enabled
- last-push approval policy remains enabled as configured
- conversation resolution remains required
- admin enforcement remains enabled
- force pushes remain disabled
- branch deletion remains disabled
- no tag is moved or deleted
- no history is rewritten

Claim boundary: this change removes a repository merge-policy blocker after automated fail-closed evidence passed. It must never be described as an independent human review or scientific approval.
