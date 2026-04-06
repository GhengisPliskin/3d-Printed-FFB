# Document Templates Reference

All templates in this file are mandatory formats. Reproduce the structure exactly when
generating project documents. Do not omit sections; write "None" or "N/A" for sections
that don't apply.

**Ground Rule 6 Reminder:** You are reading this file because you MUST read it before
generating any project document. Do not close this file and reconstruct templates from
memory.

---

## KEY_DECISION_LOG Entry

```markdown
## DECISION [#] — [Short Title]

**Status:** [Proposed | RESOLVED — Option [X] selected | Rejected | Superseded]

**Resolution:** [What is the specific action being taken?]

**Rationale:** [Why is this the optimal path?]

**FMEA Impact:** [List FMEA IDs altered/mitigated, or "None"]

**Documents updated:**
- `[Filename.ext]` — [Brief description of change]

**Downstream impact:**
- [Cascading effects, patches, or contingencies]
```

---

## CODE_DECISION_LOG Entry

```markdown
| # | Decision | Rationale | If This Breaks, Check... |
|---|----------|-----------|--------------------------|
| D-[XX] | [Brief technical description] | [Why chosen] | [Debugging heuristic] |
```

---

## CODE_DECISIONS_PATCH Entry

```markdown
# Code Decisions Patch — Phase [X]

**Status:** PROVISIONAL — not yet merged into CODE_DECISION_LOG.md
**Phase:** [X]
**Merge trigger:** Human sign-off after all phase tests pass

---

## [Category Name]

| # | Decision | Rationale | If This Breaks, Check... |
|---|----------|-----------|--------------------------|
| D-[XX] | [Brief technical description] | [Why chosen] | [Debugging heuristic] |

---

## Assumptions Register (Patch)

| # | Status | Assumption | What Breaks If Wrong |
|---|--------|-----------|----------------------|
| A-[XX] | [UNVERIFIED | CONFIRMED | INVALIDATED] | [Assumption] | [Consequence] |
```

---

## SESSION_PROMPT_HEADER

```markdown
## Session [X.Y] — [Task Name]

| | |
|---|---|
| **Task ID** | [X.Y] |
| **Component** | [Target Component/File Path] |
| **Model Tier** | [Tier 1 / Tier 2 / Tier 3] |
| **Assigned Model** | [Model name from Intelligence Roster] |
| **Depends On** | [Task IDs or "None"] |
| **Delivers To** | [Task IDs or "None"] |
| **Reference** | [ARCHITECTURE.md sections, FMEA IDs] |

### Role
[Exact persona required]

### Context
[Why this task exists. Failure modes being prevented.]

> **FMEA Constraints**
> - [ID] — [Severity] — [Rule]
> Ground Rule 8 applies: immutable during execution.

### Requirements
**R1 — [Title]**
[Details]

### Ground Rule Compliance
- **Issue Binding:** Issue #[X]
- **Decision Logging:** Write to `working/CODE_DECISIONS_PATCH.md`
- **State Sync:** [Column A] → [Column B]

> **EXIT CONDITION — Acceptance Criteria**
> - [ ] [Boolean criterion]
> - [ ] All docs updated (Rule 4)
> - [ ] All decisions logged (Rule 2)
> - [ ] Module docstrings present (Rule 11 / C-010)
```

---

## ARCHITECTURE_PATCH

```markdown
## Architecture Patch [#]

**Target Document:** `ARCHITECTURE.md`
**Triggering Decision:** [Reference]

### Section to Modify: [Heading]

**Current Text:**
[Paste current state]

**Proposed Replacement:**
[New state]

**Rationale:** [Why]

**Downstream Documents Affected:**
- [List]
```

---

## FMEA_AMENDMENT

```markdown
## FMEA Amendment Proposal [#]

**Date:** [Date]
**Submitted by:** [Name]
**Triggering Task:** [Task ID and Issue #]
**Status:** [Proposed | Approved | Rejected]

### Type
[Constraint Conflict | New Failure Mode Identified]

### Description
[What was discovered]

### Evidence
[Code, logic, or test result]

### Current Constraint (if modifying)
| ID | Current Rule | Current S | Current RPN |
|---|---|---|---|
| [FM-XXX] | [Text] | [S] | [RPN] |

### Proposed Change
| ID | Proposed Rule | S | O | D | RPN |
|---|---|---|---|---|---|
| [FM-XXX] | [Text] | [S] | [O] | [D] | [calc] |

### Impact Assessment
- **Documents affected:** [List]
- **Tasks affected:** [List]
- **Downstream risk:** [Description]

### Recommendation
[What the AI recommends. The human decides.]
```
