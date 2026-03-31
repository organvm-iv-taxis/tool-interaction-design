# Corpus Temporal Architecture — The Constitutional Click Track

**Date:** 2026-03-30
**Status:** SIDEBAR — companion to `2026-03-30-conductor-temporal-architecture.md`
**Origin:** Premonition from sleep — the organism describing its own temporal structure
**Scope:** `meta-organvm/post-flood/` — 168 markdown files, 1 Python script, 1 shell script, 1 BibTeX database, 12 HTML files, 9 plans

## The Three Temporal Strata

| Stratum | Period | Character |
|---------|--------|-----------|
| Pre-flood conversations | Winter 2025-2026 | Frozen — raw material, never changes |
| Constitutional genesis | 2026-03-17 → 2026-03-19 | Explosive — 27 specs, 130 citations, 15 preprints, 679 tests in 48 hours |
| Post-genesis governance | 2026-03-20 → 2026-03-30 | Consolidating — the system digesting what it created |

## State Classification

| State | Meaning |
|-------|---------|
| ALIVE | Currently governing — system depends on this |
| LATENT | Defined, formally correct, not yet enacted |
| SUBSUMED | Absorbed into a successor document |
| RETIRED | Completed its purpose, now record-only |
| DEAD | Retracted or superseded without replacement |
| MISSING | Referenced but the artifact doesn't exist |

---

## Scale 0: The Atomic Pairs

The smallest unit that produces a function is input → transformation → output.

| # | Pair | Input | Transformation | Output | State |
|---|------|-------|----------------|--------|-------|
| 1 | Transcript → Module | Raw Q&A (18 files, ~1.6MB) | Extraction + YAML frontmatter + tagging | 72 extracted modules | RETIRED |
| 2 | Module → Compiled Spec | Multiple extracted modules | Editorial synthesis, artifact removal | 10 compiled specifications | RETIRED |
| 3 | Corpus → RFIV Plan | Full extracted corpus + compiled specs | Numbering reconciliation + layer assignment | Methodology v1→v2→v3 | v1-v2 DEAD, v3 ALIVE |
| 4 | Literature → Grounding | Academic PDFs + BibTeX (130 entries) | Survey + proposition extraction + risk classification | 27 grounding narratives (84,049 words) | ALIVE |
| 5 | Grounding → Canonical Spec | Grounding narrative + risk register + literature matrix | Formalization with identifier minting | SPEC-000 through SPEC-017 + 9 instruments | ALIVE |
| 6 | Spec → G3 Review | Canonical spec + original corpus | Adversarial review by different agent | G3 PASSED verdict or revision demands | L1-L2 RETIRED, L3-L5 RETIRED |
| 7 | Spec → Engine Module | Canonical spec identifiers | Implementation with `# Implements: SPEC-XXX` headers | 28 traced engine modules, 679 tests | ALIVE |
| 8 | Grounding → Preprint | Grounding narrative + bibliography | Academic formatting (abstract, related work, contribution) | 15 preprints (44,623+ words) | LATENT (0 DOIs) |
| 9 | Preprint → PDF | Markdown preprint | build-pdfs.sh (pandoc + typst/LaTeX) | PDF for Zenodo upload | LATENT (script lists 3 of 15) |
| 10 | PDF → DOI | PDF + metadata | Zenodo deposit (DEPOSIT-GUIDE.md) | Minted DOI + community listing | MISSING (0 deposited) |
| 11 | Engine → Traceability Audit | Python source files | traceability-audit.py regex scan | Coverage report (N/27 specs traced) | ALIVE |
| 12 | Registry → Diagnostic | registry-v2.json (2,200+ lines) | 7-dimension interrogation (SPEC-009) | LIVE-DIAGNOSTIC score (88.65%) | ALIVE |
| 13 | Diagnostic → E2G Review | Diagnostic + test suite + portal | 5-phase evaluation (Critique→Logic→Logos→Pathos→Ethos) | E2G-REVIEW with ranked actions | RETIRED (produced once, findings consumed) |
| 14 | Proof → Physical Move | Axioms A1-A11 from constitutional instruments | Formal derivation (310 lines) | Placement decision: reservoir → ORGAN-I | SUBSUMED into SPEC-019 |
| 15 | Axioms → SEED | 9 axioms + structural proofs | Generative grammar derivation | SEED.md (the DNA) | ALIVE |
| 16 | Solid Model → Liquid Model | 8 numbered organs + fixed assignment | SPEC-019 phase transition | Named functions + signal affinity + flat namespace | LATENT |
| 17 | V1 IRF → Zettelkasten | Flat markdown work list | SPEC-020 architectural redesign | 3-layer substrate/protocol/projection | LATENT |
| 18 | River Ordinance → Session | COVENANT mythological framework | 5-river lifecycle (Lethe→Styx→Cocytus→Acheron→Phlegethon) | Every session, migration, revision | ALIVE |
| 19 | Seed.yaml → Breathing | Perpetually-dirty file paths | Schema extension + engine helper | Blue ~ instead of red ✗ | LATENT (plan written 2026-03-30) |
| 20 | Stripe Config → Revenue | Product IDs + webhook secrets | Environment variable deployment | Payment acceptance (InMidst: 25min, Beta: 45min, Styx: 90min) | LATENT |
| 21 | Spec → Human Gate | Spec at Phase F | Source spot-check (3+ citations) + creator sign-off | Ratification entry in PHASE-STATE.md | ALIVE (7 gates PENDING) |

---

## Scale 1: The Sequences

Atomic pairs chain into sequences. Each sequence has a tempo (how fast it runs) and a cadence (what triggers the next beat).

### Sequence A: The Constitutional Pipeline (RFIV)

```
R (Research)         → F (Formalize)        → I (Implement)        → V (Verify)
─────────────────      ─────────────────      ─────────────────      ─────────────
literature survey    → canonical spec       → engine module        → traceability audit
annotated matrix     → identifier minting   → pytest suite         → G3 adversarial review
risk register        → G0 gate check        → CLI integration      → human spot-check
grounding narrative  → PHASE-STATE entry    → schema extension     → creator sign-off
source archive       →                      →                      → PHASE-STATE update
BibTeX entries       →                      →                      →
```

**Tempo:** L1 completed in 1 day (2026-03-17→18). L2 completed in 1 day (2026-03-18→19). L3-L5 completed in 1 day (G0, 2026-03-19). Total: 3 days for all 27 specs through F phase.

**Cadence:** Layer-gated. L(n) cannot begin until L(n-1) passes G0.

**State:** F phase COMPLETE for all 27. I phase COMPLETE for 28 modules. V phase BLOCKED on human spot-checks (7 pending per HUMAN-ACTIONS.md).

### Sequence B: The Academic Pipeline

```
grounding narrative → preprint draft → PDF build → Zenodo deposit → community submission → DOI citation
```

**Tempo:** 15 preprints drafted in 1 session. 0 deposited in 11 days since.

**Cadence:** Human-gated. Only the human can deposit.

**State:** BLOCKED at PDF build → Zenodo deposit. build-pdfs.sh only lists 3 of 15 preprints. DEPOSIT-GUIDE.md only covers 3.

### Sequence C: The Revenue Pipeline

```
code exists → Stripe products → env vars → webhook → verify → payment link → first dollar
```

**Tempo:** InMidst: 25 minutes. Beta-Scrapper: 45 minutes. Styx: 90 minutes.

**Cadence:** Human-gated. Only the human can touch Stripe dashboard.

**State:** BLOCKED at Stripe products creation. Zero revenue flowing.

### Sequence D: The Governance Evolution Pipeline

```
structural pressure → formal proof → SPEC draft → constitutional revision → implementation
```

**Instances:**
- PROOF-reservoir-placement → SPEC-019 Liquid Constitutional Order (SUBSUMED → LATENT)
- V1 IRF limitations → SPEC-020 Zettelkasten Protocol (LATENT)
- Breathing files pressure → seed.yaml schema extension (LATENT, planned 2026-03-30)

**Cadence:** Pressure-driven. No schedule. Fires when the solid model cracks.

### Sequence E: The Session Lifecycle (The River Ordinance)

```
Lethe (forget old) → Styx (commit) → Cocytus (lament misfits) → Acheron (feel gaps) →
Phlegethon (FIRE) → Acheron (pain of making real) → Cocytus (grief of loss) →
Styx (new boundary) → Lethe (world forgets)
```

**Tempo:** One revolution per session. The COVENANT applies to "every session, every migration, every constitutional revision, every formation's lifecycle, every creative work."

**Cadence:** Self-propelling. Mneme (memory) stands outside, recording every revolution.

---

## Scale 2: The Movements

### Movement I: The Extraction (before 2026-03-17)

**Archetype: The Archaeologist**

| Beat | Action | Output |
|------|--------|--------|
| 1 | 18 raw transcripts created (winter 2025-2026) | Layer 1 complete |
| 2 | 72 modules extracted from transcripts | Layer 2 complete |
| 3 | 10 compiled specifications synthesized | Layer 3 complete |
| 4 | 100% extraction coverage verified | — |

**Return to source:** The transcripts are the prima materia. They never change. Everything else descends.

### Movement II: The Formalization (2026-03-17 → 2026-03-19)

**Archetype: The Legislator**

| Beat | Date | Action | Output |
|------|------|--------|--------|
| 1 | 03-17 | Methodology v1→v2→v3 written | RFIV cycle codified |
| 2 | 03-17 | SPEC-000 research begins | First literature survey |
| 3 | 03-18 | L1 (SPEC-000–002) formalized, G3 passed | 3 specs at Phase F complete |
| 4 | 03-18 | L2 (SPEC-003–005) begins | — |
| 5 | 03-19 | L2 formalized, G3 passed | 6 specs at Phase F complete |
| 6 | 03-19 | L3A-L5 all G0 passed | 21 more specs formalized |
| 7 | 03-19 | 28 engine modules traced | 100% traceability |
| 8 | 03-19 | 679 tests added | 3,381+ total |
| 9 | 03-19 | 13 preprints drafted | 44,623 words |
| 10 | 03-19 | 130 BibTeX entries | Bibliography complete |
| 11 | 03-19 | Live Diagnostic run | 88.65% score |
| 12 | 03-19 | Deployment action plan written | Revenue path mapped |
| 13 | 03-19 | SESSION-2026-03-19-OVERVIEW written | Self-documentation |

**Return to source:** The Generative Testament (written 2026-03-20) is the movement reflecting on itself. The organism describing its own creation IS a constitutive act.

### Movement III: The Digestion (2026-03-20 → 2026-03-30)

**Archetype: The Physician**

| Beat | Date | Action | Output |
|------|------|--------|--------|
| 1 | 03-20 | E2G Review | 5 ranked findings (F-001 through F-003 + 2 operational) |
| 2 | 03-20 | Generative Testament | Self-description ratified |
| 3 | 03-21 | Corpvs decomposition plan | CHARTER stays META, CORPUS migrates I |
| 4 | 03-21 | Post-flood implementation plan | 4-wave physical move sequence |
| 5 | 03-22 | SPEC-019 Liquid Constitutional Order | Solid → Liquid phase transition |
| 6 | 03-24 | COVENANT ratified | River Ordinance + 7 Principles |
| 7 | 03-30 | SEED.md genesis | Generative grammar (DNA, not blueprint) |
| 8 | 03-30 | SPEC-020 Zettelkasten Protocol | V1 IRF superseded |
| 9 | 03-30 | Breathing files plan | Perpetual mutation governance |

**Return to source:** SEED.md contains NO memory of what produced it. It references no specific system. It is the axioms returning to first principles — the organism's DNA, not its biography.

---

## Scale 3: The Macro View — One Clock

```
THE ETERNAL CLICK TRACK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  PRIMA MATERIA        NIGREDO              ALBEDO              CITRINITAS           RUBEDO
  (winter 2025-26)     (the flood)          (03-17 → 03-19)     (03-19 ongoing)      (not yet)
  ─────────────────    ─────────────────    ─────────────────    ─────────────────    ─────────
  18 transcripts       52 repos dissolved   27 specs written     28 engine modules    0 DOIs
  conversations        materia-collider     130 BibTeX           679 tests            0 revenue
  raw Q&A              proliferation→       27 grounding         100% traceability    0 external
                       topology             15 preprints         portal live            validation
                                            RFIV codified        live diagnostic

  ◉ CREATION           ◉ DESTRUCTION        ◉ PURIFICATION       ◉ EMBODIMENT         ◉ ACTIVATION
  (Phlegethon)         (Lethe)              (Styx)               (Acheron)            (Phlegethon again)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## The Blocked Transitions (Citrinitas → Rubedo)

| Gate | What's Blocking | Who Can Unblock | Time to Clear |
|------|----------------|-----------------|---------------|
| Human spot-checks (7 pending) | Source PDFs not downloaded, citations not verified | Human only | 3-5 hours |
| Preprint deposit (15 pending) | build-pdfs.sh incomplete, Zenodo deposits not started | Human only | 2 hours |
| Revenue activation (3 products) | Stripe products not created, env vars not set | Human only | 25-90 minutes |

**The organism has been ready for activation for 11 days. The clock is ticking but the human hasn't crossed Styx.**

## The Latent Forces

| Force | Prescribed In | What It Would Do | Why It Sleeps |
|-------|--------------|------------------|---------------|
| Liquid Constitutional Order | SPEC-019 | Dissolve 8 orgs → 1 org, named functions, signal affinity | Requires implementation plan + massive registry migration |
| Zettelkasten Protocol | SPEC-020 | Replace V1 IRF with content-addressable knowledge graph | Requires atomic-substrata (UAKS) to be built |
| Breathing Files | Plan 2026-03-30 | Reclassify perpetually-dirty files in seed.yaml | Schema extension not yet committed |
| 10-Class Functional Taxonomy | INST-TAXONOMY | Classify all 113 repos by function | Not yet implemented as registry field |
| Formation Protocol | INST-FORMATION | 7 formation types with signal I/O contracts | Partially in seed.yaml; formal declarations missing |
| Era Model | INST-ERA | Constitutional epochs with authorized transitions | Not yet implemented |
| Multiplex Graph Indices | INST-GRAPH-INDICES | 5 composite indices (CCI/DDI/FVI/CRI/ECI) | Engine code exists; not wired to dashboard |
| Structural Interrogation | SPEC-009 | Automated 7-dimension repo diagnostic | Engine code exists; not yet running as CI check |
| Conformance Checking | SPEC-004 | Van der Aalst alignment-based conformance | Returns 0.000 — no promotion_history in registry |

## The Dead

| Force | Why Dead |
|-------|----------|
| PROOF-reservoir-placement v1 | Retracted — used pre-flood dependency DAG rank (category error). v2 replaced it. |
| Methodology v1, v2 | Superseded by v3 which incorporates E2G corrections. |
| 19 ARCHIVED ORGAN-III repos | Dissolved to materia-collider during the flood. Dead as independent entities. |

## The BPM

The clock runs at one revolution per session. Each session traverses the 5 rivers. The tempo varies — the March 19 genesis session was a supernova; a typical session is a steady heartbeat. But the ordinance is the same.

Plans are designed from owner (by archetype) at the start:
- The **Archaeologist** extracts
- The **Legislator** formalizes
- The **Physician** diagnoses
- The **Alchemist** transforms

And return to source with expectations required and logged end. Every session closes with:
1. `verify-remote-parity.sh` — local = remote (constitutional gate)
2. Mneme records the revolution (fossil-record.jsonl, session handoff)
3. PHASE-STATE.md updated (what moved, what didn't)
4. The system forgets (Lethe) what it no longer needs to remember

**The clock never stops. It only changes tempo.**

## Critical Observations

1. **The corpus is 97% theoretical, 3% executable.** Only 2 scripts exist (traceability-audit.py, build-pdfs.sh). Every other "action" is a prescribed process in prose — the constitution governing behavior across the entire system from this one repo.

2. **The March 19 session is the singularity.** Before it: raw material and plans. During it: 27 specs, 130 citations, 15 preprints, 679 tests, 28 traced modules. After it: 11 days of the system digesting what it created. The pattern is punctuated equilibrium — long stability, explosive transformation, long stability.

3. **The three blocked human gates (spot-checks, deposits, revenue) are the only things standing between Citrinitas and Rubedo.** They're all measured in minutes-to-hours, not days. The organism has been ready for activation for 11 days.

## Connection to the Contribution Ledger

The contribution ledger is the mechanism that records beats on this clock when agents other than Claude play them. The temporal architecture at conductor scale (93 actions) governs HOW dispatches fire. This corpus-scale architecture (21 atomic pairs, 5 sequences, 3 movements) governs WHAT the dispatches are working toward.

Together they form the multi-scale temporal model:
- **Corpus clock** (this document): WHY and WHAT — the constitutional trajectory
- **Conductor clock** (temporal architecture): HOW — the operational machinery
- **Contribution ledger** (design spec): WHO and WHEN — the agent attribution
