# Process Operating System

This directory contains the canonical execution system for disciplined software delivery.

## Layout
- `contracts/`: machine-validated interfaces for work items, sprint reports, release readiness, and scorecards.
- `templates/`: ready-to-use YAML examples that satisfy the contracts.
- `playbooks/`: short SOPs for each delivery phase.
- `risk/`: pre-mortem and recovery drill templates.
- `roadmap/`: 90-day implementation plan and measurable outcomes.
- `scorecards/`: weekly KPI schema and examples.

## Core Loop
`Discover -> Design -> Build -> Verify -> Release -> Operate`

Each work item must satisfy Definition of Done (tests, docs, changelog, demo evidence) before closure.

## Validation
Run:

```bash
python tools/validate_process_assets.py
```

This command validates templates against JSON Schemas and checks playbook/risk assets for required sections.

For full local gates:

```bash
./tools/run_quality_gate.sh
```
