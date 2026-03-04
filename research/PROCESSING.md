# Research Processing Pipeline

## Directory Structure

```
research/
├── inbox/        ← Drop documents here
├── digested/     ← Analyzed, extracted, cross-referenced
├── implemented/  ← Changes applied to ontology/routing/DSL/router
```

## Processing Stages

### 1. INBOX → INGEST
- Document lands in `inbox/`
- Full read and comprehension
- Extract: new tools, capabilities, protocols, data types, routes, workflow patterns

### 2. INGEST → DIGEST (`digested/`)
- Create `digested/{document-slug}.yaml` with structured extraction:
  - New clusters or tools to add to existing clusters
  - New routes discovered
  - New workflow patterns
  - Capability gaps identified
  - Conflicts with existing ontology
- Cross-reference against current `ontology.yaml` and `routing-matrix.yaml`

### 3. DIGEST → IMPLEMENT (`implemented/`)
- Apply changes to:
  - `ontology.yaml` — new/modified clusters, capabilities, data types
  - `routing-matrix.yaml` — new routes, alternatives, capability routing
  - `workflow-dsl.yaml` — new example workflows
  - `graph.mmd` — updated visual
  - `router.py` — new commands or logic if needed
- Move digest file to `implemented/` with implementation notes appended
- Validate: `python3 router.py validate` + `python3 router.py clusters`

## Naming Convention

```
inbox/       {original-filename}.{ext}
digested/    YYYY-MM-DD-{slug}-digest.yaml
implemented/ YYYY-MM-DD-{slug}-digest.yaml  (moved, with impl notes)
```
