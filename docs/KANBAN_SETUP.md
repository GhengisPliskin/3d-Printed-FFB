# Kanban Board Configuration

## Board: 3D-Printed-FFB

### Columns

| Column | Purpose | WIP Limit | Entry Criteria | Exit Criteria |
|---|---|---|---|---|
| Backlog | New issues awaiting specification | None | Issue created | Task decomposed, dependencies identified |
| Ready | Fully specified, unblocked tasks | 10 | Prompt header generated, dependencies met | Assigned to developer/agent |
| In Progress | Actively being worked | 2 | Assigned, Kanban state announced (Rule 3) | All acceptance criteria met |
| In Review | Awaiting human review | 5 | PR opened or artifact submitted | Review approved |
| Done | Completed and documented | None | Review approved, docs updated (Rule 4), patch merged (Rule 2) | N/A |

### Spike Constraint (Ground Rule 7)

Issues labeled `spike` are prohibited from moving to "Done." They may only reach
"Done" after a linked formalization issue is created and itself reaches "In Review."

Enforcement is two-layer:

**Layer 1 — GitHub Project Automation (visual friction)**
In the GitHub Projects UI under "Workflows":
- Trigger: Item moved to "Done" with label `spike`
- Action: Move back to "In Review"

**Layer 2 — GitHub Actions CI check (hard enforcement)**
Defined in `.github/workflows/spike-check.yml`. Triggers on `issues.closed`.
Re-opens the issue and posts a comment if no linked formalization issue is found.

### Automation Rules
- When PR is opened → move card to "In Review"
- When PR is merged → move card to "Done"
- When issue is labeled `blocked` → move card to "Blocked"
- When issue has label `spike` and moves to "Done" → move back to "In Review" (Layer 1)
- When issue with label `spike` is closed without linked formalization issue → re-open and comment (Layer 2)

### Label Taxonomy

**Phase** — one per issue, required:
`phase:0`, `phase:1`, `phase:2`

**Boundary** — one per issue, required:
`human-gate`, `ai-eligible`, `ai-with-review`

**Type** — one per issue, required:
`task`, `spike`, `decision`, `amendment`

**Priority** — one per issue, optional (default: `normal`):
`critical`, `high`, `normal`
