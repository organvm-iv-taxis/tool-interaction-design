# Gap Ledger

Status snapshot date: 2026-03-04

## Ownership Gaps
- [ ] Every active work item has a named owner.
  Evidence: no repository-wide enforced work-item registry yet.
- [ ] Every release candidate has a release captain.
  Evidence: release-readiness contract exists but is not yet mandatory in CI.

## Workflow Gaps
- [ ] Intake and design artifacts are linked on every work item.
  Evidence: playbooks/contracts exist; historical and new work are not yet uniformly tracked.
- [ ] Verification evidence is attached before closure.
  Evidence: DoD requires evidence, but enforcement is currently by convention plus validator templates.

## Control Gaps
- [ ] Policy simulation evidence exists per release.
  Evidence: policy simulation runs locally; no required CI gate in release workflow yet.
- [ ] Observability trend checks run in CI.
  Evidence: trend checks run in local quality gate script; not yet a dedicated CI step.
- [ ] Recovery drill performed at least once per sprint.
  Evidence: checklist exists, but no recorded recurring drill history yet.

## Documentation Gaps
- [x] SOPs are one-screen and current.
  Evidence: playbook pack created under `process/playbooks/`.
- [ ] Incident runbook updated after each postmortem.
  Evidence: incident playbook exists; postmortem update loop not yet operationalized.
