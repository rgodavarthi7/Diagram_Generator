# Diagram Generator

Excalidraw diagram generator with an autoresearch-style prompt optimization loop.

## Project Structure

- `autoresearch.py` — Main generate → evaluate → mutate loop (Claude Sonnet on Bedrock for generation/mutation, Claude Haiku for eval)
- `dashboard.py` — Live web dashboard for tracking optimization runs
- `validate_diagram.py` — Validates `.excalidraw` JSON files against project rules
- `data/output/` — Generated Excalidraw diagram files
- `data/prompt.txt` — Current prompt being optimized
- `data/best_prompt.txt` — Best prompt found so far
- `data/state.json` — Loop state
- `data/results.jsonl` — Experiment log

## Commands

- `/diagram <description>` — Generate an Excalidraw diagram. Auto-selects linear (left-to-right) or flowchart (top-to-bottom with decisions) layout based on description
- `python validate_diagram.py <path>` — Validate a diagram file (7 checks)
- `python autoresearch.py --once` — Run a single optimization cycle
- `python dashboard.py --port 8501` — Start the live dashboard

## Key Conventions

- All generated diagrams go in `data/output/` with the naming pattern `{slug}-workflow.excalidraw`
- Always validate diagrams after generating with `python validate_diagram.py`
- Excalidraw elements must include ALL required fields (seed, version, opacity, points, boundElements, appState, etc.) or they won't render in the VS Code extension
- Two layout modes: **Linear** (simple sequential workflows) and **Flowchart** (decisions, branches, merges, loops)
- Flowchart element types: rectangle (process), diamond (decision), ellipse (start/end terminal)
- Decision diamonds must have at least 2 outgoing arrows with labels ("Yes"/"No")
- Arrow labels are text elements with `containerId` pointing to the arrow
- Flowchart layout uses a column/row grid: column 0 = main flow, +/-1 = branches
- Diagram labels: 1-3 words, no digits
- Color palette is strict — only use the 6 pastel/stroke pairs defined in the diagram skill

## Autoresearch Evaluation Criteria (8 total, max 80 per batch)

| Criterion | What it checks |
|-----------|---------------|
| symbol_correctness | Diamonds for decisions, ellipses for terminals, rectangles for processes |
| label_clarity | Verb phrases for processes, condition form for decisions, Yes/No on arrows, no digits |
| flow_direction | Primary path top-to-bottom, max 20% upward arrows (loops only) |
| no_overlap | Zero bounding-box intersections, minimum 40px spacing |
| branch_completeness | Every diamond has 2+ labeled arrows, every path reaches End (no dead ends) |
| edge_crossings | Arrow paths don't intersect (< 10% crossing ratio allowed) |
| color_semantics | Yellow=decisions, orange=errors, blue=start, pink=end |
| node_density | 5-15 shapes, max 3 decision diamonds |

Each criterion: programmatic check + Claude Haiku eval → min(both) = final score.

## Environment

- AWS Bedrock for Claude Sonnet (generation/mutation) and Claude Haiku (eval)
- Credentials in `.env` (not committed)
