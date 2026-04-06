# Master Project Plan Template

Reproduce this structure exactly when generating a Master Plan. Populate every section.
Mark sections as "[TBD — requires user input]" only if the user explicitly deferred.

**Ground Rule 6 Reminder:** Read this file before generating a Master Plan.

---

```markdown
# Master Project Plan — [Project Name]

**Generated:** [Date]
**Status:** [Draft | Under Review | Confirmed]
**Version:** [1.0]

---

## 1. Project Intelligence Roster

| Tier | Role | Assigned Model(s) | Max Context Window | Notes |
|---|---|---|---|---|
| Tier 1 | Complex Reasoning | [Human-defined] | [Human-defined] | |
| Tier 2 | Standard Execution | [Human-defined] | [Human-defined] | |
| Tier 3 | Boilerplate | [Human-defined] | [Human-defined] | |

### Context Window Implications
- Prompt headers must not exceed [Y] tokens of preamble.
- Repomix config must exclude files to fit the smallest active context window.

---

## 2. Project Overview

### 2.1 Purpose
[One-paragraph description.]

### 2.2 Stakeholders
| Role | Name / Team | Responsibilities |
|---|---|---|
| [Owner] | [Name] | [Responsibilities] |

### 2.3 Success Criteria
[3-5 measurable outcomes.]

---

## 3. Requirements

### 3.1 Functional Requirements
| ID | Requirement | Priority | Source |
|---|---|---|---|
| FR-001 | [Description] | [Must/Should/Could] | [Source] |

### 3.2 Non-Functional Requirements
| ID | Requirement | Category | Threshold |
|---|---|---|---|
| NFR-001 | [Description] | [Category] | [Target] |

### 3.3 Constraints
| ID | Constraint | Type | Impact |
|---|---|---|---|
| C-001 | [Description] | [Type] | [Impact] |

---

## 4. Architecture & Directory Structure

### 4.1 High-Level Architecture
[2-3 paragraphs describing system architecture.]

### 4.2 Directory Structure
[Tree diagram]

### 4.3 Component Descriptions
| Component | Responsibility | Interfaces | Key Files |
|---|---|---|---|
| [Name] | [What] | [Talks to] | [Paths] |

---

## 5. Risk Register (FMEA)

| ID | Failure Mode | Potential Effect | S | O | D | RPN | Mitigation | Status |
|---|---|---|---|---|---|---|---|---|
| FM-001 | [Description] | [Consequence] | [1-10] | [1-10] | [1-10] | [calc] | [Plan] | [Open] |

**Action threshold:** RPN >= 100 requires mitigation before dependent tasks begin.

---

## 6. Task Registry

| Task ID | Task Name | Component | Complexity | Tier | Depends On | Delivers To | FMEA Refs | Boundary | Phase |
|---|---|---|---|---|---|---|---|---|---|
| 0.1 | [Name] | [Component] | [L/M/H] | [1/2/3] | [IDs] | [IDs] | [FM-XXX] | [boundary] | [0/1/2] |

---

## 7. Kanban Board Configuration

See docs/KANBAN_SETUP.md for full configuration.

---

## 8. Operational Ground Rules

| # | Rule | Enforcement |
|---|---|---|
| 1 | Issue Binding | PR template requires Issue reference |
| 2 | Decision Logging | PR checklist includes log verification |
| 3-11 | [See CLAUDE.md and CONTRIBUTING.md] | |

---

## 9. Documentation Framework

| Document | Status | Initial Content Source |
|---|---|---|
| README.md | [Status] | [Source] |
| ARCHITECTURE.md | [Status] | [Source] |

---

## 10. Phase 0 Decisions

### DECISION 1 — [Title]
**Status:** [Proposed | RESOLVED]
**Resolution:** [What]
**Rationale:** [Why]
**FMEA Impact:** [IDs or "None"]
```
