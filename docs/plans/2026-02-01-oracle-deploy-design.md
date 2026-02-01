# ORACLE Deployment Environment (GitHub Actions)

## Context
The deployment workflow currently targets two VPS environments (CC and DMIT) via a matrix in `.github/workflows/deploy.yml`. The user wants to add ORACLE support with identical behavior and no environment-specific differences.

## Decision
Add `ORACLE` as a third entry in the existing matrix. Keep all steps unchanged so ORACLE uses the same deploy flow, secrets, and gating rules as CC/DMIT.

## Scope
In-scope:
- Update the matrix in `.github/workflows/deploy.yml` from `[CC, DMIT]` to `[CC, DMIT, ORACLE]`.
- Rely on a GitHub Environment named `ORACLE` for its secrets and protections.

Out-of-scope:
- Any Oracle-specific variations to deploy steps, secrets, or infrastructure.
- Changes to application code or runtime behavior.

## Expected Behavior
- A job will run for `matrix.environment == ORACLE` on push or manual dispatch.
- The job will pull secrets from the `ORACLE` environment and follow the same setup/deploy path as CC/DMIT.
- If required secrets are missing in `ORACLE`, the job will fail similarly to CC/DMIT.

## Risks and Mitigations
- **Missing secrets in ORACLE environment**: Document required secrets in the environment settings before running.
- **Parallel deploy conflicts**: Unchanged; ORACLE runs in parallel like existing environments.

## Verification
- No automated tests required for workflow matrix update.
- Manual confirmation by running a workflow_dispatch and observing the ORACLE job starts and attempts deployment.
