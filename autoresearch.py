#!/usr/bin/env python3
"""
Autoresearch Diagrams -- Self-improving prompt optimization.
Pattern (inspired by karpathy/autoresearch):
  generate (Claude/Bedrock -> Excalidraw JSON) -> eval (programmatic + Claude) -> keep/discard -> mutate -> repeat
"""

import argparse
import io
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import boto3
import anthropic
from dotenv import load_dotenv

# Fix Windows console encoding for Unicode output from Claude
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

load_dotenv()

# -- Paths ----------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DIAGRAMS_DIR = DATA_DIR / "diagrams"
PROMPT_FILE = DATA_DIR / "prompt.txt"
BEST_PROMPT_FILE = DATA_DIR / "best_prompt.txt"
STATE_FILE = DATA_DIR / "state.json"
RESULTS_FILE = DATA_DIR / "results.jsonl"

# -- Constants ------------------------------------------------------------------
CLAUDE_GEN_MODEL = "us.anthropic.claude-sonnet-4-6"               # generation + mutation
CLAUDE_EVAL_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"  # eval (cheaper)
DIAGRAMS_PER_RUN = 10
LOOP_INTERVAL_SECONDS = 120

# Topics that require flowchart logic (decisions, branches, error handling)
DIAGRAM_TOPICS = [
    "API request lifecycle: receive request, check auth (if invalid return unauthorized), parse body, check rate limit (if exceeded return too many requests), route to service, return response",
    "user login flow: enter credentials, validate (if invalid show error and retry), check MFA enabled (if yes send code and verify), create session, redirect to dashboard",
    "payment processing: receive order, validate card (if declined notify customer), check fraud score (if suspicious flag for review), charge card, send confirmation, fulfill order",
    "CI/CD pipeline: push code, run linting (if fails notify developer), run tests (if fails block merge), build artifact, deploy to staging, run smoke tests (if fails rollback), deploy to production",
    "file upload flow: select file, validate format (if invalid show error), check file size (if too large reject), scan for malware (if detected quarantine), upload to storage, return URL",
    "order fulfillment: receive order, check inventory (if out of stock backorder), reserve items, process payment (if fails release reservation), pack shipment, ship, send tracking email",
    "incident response: alert triggered, assess severity (if low auto-resolve), page oncall, investigate root cause, apply fix, verify resolution (if not resolved escalate), close incident",
    "database migration: backup current state, apply schema changes, validate migration (if errors rollback from backup), run data integrity checks (if fails pause and alert), update application config, switch traffic",
    "user registration: submit form, validate email format (if invalid show error), check if user exists (if yes prompt login), hash password, create account, send verification email, activate on confirm",
    "feature flag rollout: create flag, deploy to canary (if error rate spikes disable flag), expand to ten percent, monitor metrics (if degraded rollback), expand to fifty percent, expand to all users",
]

SEED_PROMPT = """\
You are an expert at creating Excalidraw flowchart diagrams for software engineers. Generate a valid Excalidraw JSON file for the topic described below.

OUTPUT: ONLY valid JSON (no markdown fences, no explanation).

TOP-LEVEL STRUCTURE:
{"type": "excalidraw", "version": 2, "source": "https://excalidraw.com", "elements": [...], "appState": {"gridSize": null, "viewBackgroundColor": "#ffffff"}, "files": {}}

ELEMENT TYPES — use the correct shape for each role:
- "ellipse" for Start/End terminals (width: 120, height: 60)
- "diamond" for decision points / if-then-else (width: 140, height: 140, roundness: {"type": 2})
- "rectangle" for process steps (width: 160, height: 80, roundness: {"type": 3})
- "text" for labels inside shapes (containerId must reference parent)
- "arrow" for connections (with startBinding/endBinding referencing shapes)

COLOR SEMANTICS — use colors with meaning:
- Start terminal: #a5d8ff background, #1971c2 stroke (blue)
- End terminal: #fcc2d7 background, #c2255c stroke (pink)
- Decision diamonds: #fff3bf background, #f08c00 stroke (yellow)
- Process steps: cycle through #d0bfff/#6741d9 (purple), #b2f2bb/#2f9e44 (green)
- Error/failure steps: #ffd8a8 background, #e8590c stroke (orange)

LAYOUT — top-to-bottom flowchart:
- Primary/happy path flows straight DOWN in column 0 (center x = 400)
- ROW_HEIGHT = 200px between node centers, BASE_Y = 60
- Decision "Yes" branch goes DOWN (same column), "No" branch goes RIGHT (column +1, offset 300px) or LEFT (column -1)
- Error/failure nodes go to side columns
- All branches merge back to a single End terminal at the bottom via bent arrows
- Node position: x = 400 + (col * 300) - (width / 2), y = 60 + (row * 200)

ARROWS:
- Vertical (same column): points = [[0,0], [0, gap]], width = 0
- Bent (branch): points = [[0,0], [dx, 0], [dx, dy]] for L-shaped paths
- Merge (side to main): points = [[0,0], [0, partial], [dx, total]] to reconnect
- Every arrow from a diamond MUST have a label text element with containerId = arrow id
- Arrow labels: "Yes", "No", "Error", "Retry" — fontSize 14

REQUIRED FIELDS ON EVERY ELEMENT (missing fields cause silent render failure):
angle, strokeColor, backgroundColor, fillStyle ("solid"), strokeWidth (2), strokeStyle ("solid"),
roughness (1), opacity (100), seed (unique random int), version (1), versionNonce (unique int),
isDeleted (false), groupIds ([]), boundElements (array of {id, type}), link (null), locked (false)

TEXT ELEMENTS also need: fontSize, fontFamily (1), textAlign ("center"), verticalAlign ("middle"),
containerId, originalText (copy of text), lineHeight (1.25)

ARROW ELEMENTS also need: points array, startBinding, endBinding, startArrowhead (null), endArrowhead ("arrow")

CRITICAL RULES:
- Every diagram MUST have exactly one Start ellipse and one End ellipse
- Every diamond MUST have exactly 2 outgoing arrows with Yes/No labels
- Every path must reach the End terminal (no dead ends)
- Process labels: verb phrases, 1-3 words ("Validate Input", "Send Email")
- Decision labels: condition form, 1-2 words ("Auth Valid", "In Stock")
- ZERO digits anywhere in any text
- boundElements on shapes must list their text label AND all connected arrows
- 5-15 total shape nodes per diagram (not counting text or arrows)
"""

EVAL_SYSTEM_PROMPT = """You are an expert Excalidraw flowchart evaluator for software engineering diagrams. You will receive an Excalidraw JSON file.
Score it on exactly these 8 binary criteria (1 = pass, 0 = fail):

1. symbol_correctness: Diamonds used for decisions, ellipses for start/end, rectangles for processes. No shape type misuse.
2. label_clarity: Process labels use verb phrases ("Validate Input"), decision labels use condition form ("Auth Valid"), arrow labels say "Yes"/"No". All text is readable and correctly spelled.
3. flow_direction: Primary path flows top-to-bottom. Only loop-backs go upward. No ambiguous diagonal arrows.
4. no_overlap: No elements visually overlap. Adequate spacing between all nodes.
5. branch_completeness: Every diamond has exactly 2 labeled outgoing arrows. Every path reaches an End terminal (no dead ends).
6. edge_crossings: Arrow paths do not intersect or cross each other.
7. color_semantics: Colors carry meaning: yellow for decisions, orange for errors, blue for start, pink for end. Not randomly assigned.
8. node_density: Diagram has 5-15 shape nodes (not counting text/arrows). No more than 3 decision diamonds.

Respond ONLY with valid JSON:
{"symbol_correctness": 0|1, "label_clarity": 0|1, "flow_direction": 0|1, "no_overlap": 0|1, "branch_completeness": 0|1, "edge_crossings": 0|1, "color_semantics": 0|1, "node_density": 0|1, "notes": "<brief one-sentence observation>"}"""

MUTATION_SYSTEM_PROMPT = """You are an expert prompt engineer specializing in Excalidraw JSON diagram generation prompts.
You will receive the current best prompt and evaluation feedback showing which criteria scored lowest.
Rewrite the prompt to strengthen the weak criteria while preserving what already works.
Return ONLY the new prompt text, no preamble or explanation."""


# -- Helpers --------------------------------------------------------------------

def ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DIAGRAMS_DIR.mkdir(parents=True, exist_ok=True)


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"run_number": 0, "best_score": 0, "baseline_score": None}


def save_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def load_prompt() -> str:
    if PROMPT_FILE.exists():
        return PROMPT_FILE.read_text(encoding="utf-8").strip()
    PROMPT_FILE.write_text(SEED_PROMPT, encoding="utf-8")
    return SEED_PROMPT


def save_prompt(prompt: str):
    PROMPT_FILE.write_text(prompt, encoding="utf-8")


def save_best_prompt(prompt: str):
    BEST_PROMPT_FILE.write_text(prompt, encoding="utf-8")


def load_best_prompt() -> str:
    if BEST_PROMPT_FILE.exists():
        return BEST_PROMPT_FILE.read_text(encoding="utf-8").strip()
    return load_prompt()


# -- Clients --------------------------------------------------------------------

def init_bedrock() -> anthropic.AnthropicBedrock:
    """Use the default credential chain via a boto3 session (supports SSO)."""
    session = boto3.Session(
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )
    creds = session.get_credentials().get_frozen_credentials()
    return anthropic.AnthropicBedrock(
        aws_access_key=creds.access_key,
        aws_secret_key=creds.secret_key,
        aws_session_token=creds.token,
        aws_region=session.region_name,
    )


# -- Programmatic eval helpers ------------------------------------------------─

def _hex_to_hsl(hex_color: str) -> tuple[float, float, float] | None:
    """Convert #RRGGBB to (H, S, L) with H in [0,360], S/L in [0,1]."""
    hex_color = hex_color.strip().lstrip("#")
    if len(hex_color) != 6:
        return None
    try:
        r, g, b = int(hex_color[0:2], 16) / 255, int(hex_color[2:4], 16) / 255, int(hex_color[4:6], 16) / 255
    except ValueError:
        return None
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2
    if mx == mn:
        h = s = 0.0
    else:
        d = mx - mn
        s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
        if mx == r:
            h = (g - b) / d + (6 if g < b else 0)
        elif mx == g:
            h = (b - r) / d + 2
        else:
            h = (r - g) / d + 4
        h *= 60
    return h, s, l


ALLOWED_PASTELS = {
    "#a5d8ff", "#d0bfff", "#b2f2bb", "#ffd8a8", "#fcc2d7", "#fff3bf",
}

# Expected color-to-role mapping for color_semantics check
COLOR_ROLE_MAP = {
    "#fff3bf": "diamond",    # yellow = decision
    "#ffd8a8": "rectangle",  # orange = error step
    "#a5d8ff": "ellipse",    # blue = start terminal
    "#fcc2d7": "ellipse",    # pink = end terminal
}

CRITERIA = [
    "symbol_correctness", "label_clarity", "flow_direction", "no_overlap",
    "branch_completeness", "edge_crossings", "color_semantics", "node_density",
]


def _get_shapes(elements: list[dict]) -> list[dict]:
    return [el for el in elements if el.get("type") in ("rectangle", "ellipse", "diamond")]


def _get_arrows(elements: list[dict]) -> list[dict]:
    return [el for el in elements if el.get("type") == "arrow"]


def _get_bbox(el: dict) -> tuple[float, float, float, float]:
    """Return (x1, y1, x2, y2) bounding box."""
    x = el.get("x", 0)
    y = el.get("y", 0)
    return (x, y, x + el.get("width", 0), y + el.get("height", 0))


def check_symbol_correctness(elements: list[dict]) -> bool:
    """Diamonds for decisions, ellipses for terminals, rectangles for processes."""
    shapes = _get_shapes(elements)
    if not shapes:
        return False
    has_ellipse = any(s.get("type") == "ellipse" for s in shapes)
    has_diamond = any(s.get("type") == "diamond" for s in shapes)
    has_rect = any(s.get("type") == "rectangle" for s in shapes)
    # A proper flowchart needs at least terminals + decisions + processes
    return has_ellipse and has_diamond and has_rect


def check_label_clarity(elements: list[dict]) -> bool:
    """All text elements have non-empty, short, readable labels. Arrow labels on decisions exist."""
    text_els = [el for el in elements if el.get("type") == "text"]
    if not text_els:
        return False
    for el in text_els:
        text = (el.get("text", "") or "").strip()
        if not text:
            return False
        if len(text) > 40:
            return False
        # No digits allowed
        if re.search(r'\d', text):
            return False
    # Check that arrows from diamonds have labels
    diamonds = {el["id"] for el in elements if el.get("type") == "diamond"}
    if not diamonds:
        return True
    arrows_from_diamonds = [
        el for el in elements
        if el.get("type") == "arrow"
        and (el.get("startBinding") or {}).get("elementId") in diamonds
    ]
    arrow_ids_from_diamonds = {a["id"] for a in arrows_from_diamonds}
    labeled_arrows = {
        el.get("containerId") for el in text_els
        if el.get("containerId") in arrow_ids_from_diamonds
    }
    # Every arrow from a diamond should have a label
    return arrow_ids_from_diamonds == labeled_arrows


def check_flow_direction(elements: list[dict]) -> bool:
    """Primary flow goes top-to-bottom. Most arrows should point downward or sideways, not upward."""
    arrows = _get_arrows(elements)
    if not arrows:
        return False
    downward_or_sideways = 0
    upward = 0
    for a in arrows:
        points = a.get("points", [])
        if len(points) < 2:
            continue
        # Check overall vertical direction (last point vs first)
        dy = points[-1][1] - points[0][1]
        if dy >= -10:  # going down or roughly horizontal (allow small tolerance for horizontal)
            downward_or_sideways += 1
        else:
            upward += 1
    total = downward_or_sideways + upward
    if total == 0:
        return False
    # Allow up to 20% upward arrows (for loops/retries)
    return upward <= total * 0.2


def check_no_overlap(elements: list[dict]) -> bool:
    """No shape bounding boxes overlap. Minimum 40px spacing between shapes."""
    shapes = _get_shapes(elements)
    min_gap = 40
    for i in range(len(shapes)):
        ax1, ay1, ax2, ay2 = _get_bbox(shapes[i])
        for j in range(i + 1, len(shapes)):
            bx1, by1, bx2, by2 = _get_bbox(shapes[j])
            # Check overlap (with min_gap padding)
            if (ax1 - min_gap < bx2 and ax2 + min_gap > bx1 and
                    ay1 - min_gap < by2 and ay2 + min_gap > by1):
                # Bounding boxes are within min_gap of each other — check if truly overlapping
                if ax1 < bx2 and ax2 > bx1 and ay1 < by2 and ay2 > by1:
                    return False  # actual overlap
    return True


def check_branch_completeness(elements: list[dict]) -> bool:
    """Every diamond has 2+ outgoing arrows. Every path reaches an End terminal (no dead ends)."""
    diamonds = {el["id"] for el in elements if el.get("type") == "diamond"}
    if not diamonds:
        return False  # flowchart must have decisions
    # Check diamond outgoing arrows
    arrow_sources: dict[str, list[str]] = {}
    arrow_targets: dict[str, list[str]] = {}
    for el in elements:
        if el.get("type") != "arrow":
            continue
        src = (el.get("startBinding") or {}).get("elementId")
        tgt = (el.get("endBinding") or {}).get("elementId")
        if src:
            arrow_sources.setdefault(src, []).append(tgt or "")
        if tgt:
            arrow_targets.setdefault(tgt, []).append(src or "")
    for d_id in diamonds:
        if len(arrow_sources.get(d_id, [])) < 2:
            return False
    # Check all non-End shapes have outgoing arrows (no dead ends except End terminals)
    shapes = _get_shapes(elements)
    end_terminals = {
        el["id"] for el in shapes
        if el.get("type") == "ellipse"
        and any(
            t.get("containerId") == el["id"] and "end" in (t.get("text", "") or "").lower()
            for t in elements if t.get("type") == "text"
        )
    }
    for s in shapes:
        sid = s.get("id", "")
        if sid in end_terminals:
            continue
        if not arrow_sources.get(sid):
            return False  # dead end (non-End shape with no outgoing arrow)
    return True


def check_edge_crossings(elements: list[dict]) -> bool:
    """Check that arrow paths don't intersect each other. Allow up to 10% crossing ratio."""
    arrows = _get_arrows(elements)
    if len(arrows) < 2:
        return True

    # Build absolute line segments for each arrow
    def get_segments(arrow: dict) -> list[tuple[tuple[float, float], tuple[float, float]]]:
        ax = arrow.get("x", 0)
        ay = arrow.get("y", 0)
        points = arrow.get("points", [])
        if len(points) < 2:
            return []
        abs_points = [(ax + p[0], ay + p[1]) for p in points]
        return [(abs_points[i], abs_points[i + 1]) for i in range(len(abs_points) - 1)]

    def segments_cross(s1, s2) -> bool:
        """Check if two line segments intersect using cross product method."""
        (x1, y1), (x2, y2) = s1
        (x3, y3), (x4, y4) = s2

        def cross(o, a, b):
            return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

        d1 = cross((x3, y3), (x4, y4), (x1, y1))
        d2 = cross((x3, y3), (x4, y4), (x2, y2))
        d3 = cross((x1, y1), (x2, y2), (x3, y3))
        d4 = cross((x1, y1), (x2, y2), (x4, y4))

        if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and \
           ((d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)):
            return True
        return False

    crossings = 0
    all_segments = []
    for a in arrows:
        segs = get_segments(a)
        all_segments.append((a.get("id"), segs))

    for i in range(len(all_segments)):
        for j in range(i + 1, len(all_segments)):
            for s1 in all_segments[i][1]:
                for s2 in all_segments[j][1]:
                    if segments_cross(s1, s2):
                        crossings += 1

    total_edges = len(arrows)
    return crossings <= total_edges * 0.1


def check_color_semantics(elements: list[dict]) -> bool:
    """Colors carry meaning: yellow=decisions, orange=errors, blue=start, pink=end."""
    shapes = _get_shapes(elements)
    if not shapes:
        return False
    # All backgrounds should be from allowed palette
    for s in shapes:
        bg = (s.get("backgroundColor") or "").lower()
        if bg and bg != "transparent" and bg not in ALLOWED_PASTELS:
            hsl = _hex_to_hsl(bg)
            if hsl and hsl[2] < 0.65:
                return False  # dark color
    # Check that diamonds use yellow
    for s in shapes:
        if s.get("type") == "diamond":
            bg = (s.get("backgroundColor") or "").lower()
            if bg != "#fff3bf":
                return False
    # Check that ellipses use blue or pink
    ellipse_colors = {"#a5d8ff", "#fcc2d7"}
    for s in shapes:
        if s.get("type") == "ellipse":
            bg = (s.get("backgroundColor") or "").lower()
            if bg not in ellipse_colors:
                return False
    return True


def check_node_density(elements: list[dict]) -> bool:
    """5-15 shape nodes, no more than 3 decision diamonds."""
    shapes = _get_shapes(elements)
    diamonds = [s for s in shapes if s.get("type") == "diamond"]
    count = len(shapes)
    return 5 <= count <= 15 and len(diamonds) <= 3


def programmatic_eval(excalidraw_data: dict) -> dict:
    """Run the 8 programmatic checks on an Excalidraw JSON. Returns scores dict."""
    elements = excalidraw_data.get("elements", [])
    return {
        "symbol_correctness": 1 if check_symbol_correctness(elements) else 0,
        "label_clarity": 1 if check_label_clarity(elements) else 0,
        "flow_direction": 1 if check_flow_direction(elements) else 0,
        "no_overlap": 1 if check_no_overlap(elements) else 0,
        "branch_completeness": 1 if check_branch_completeness(elements) else 0,
        "edge_crossings": 1 if check_edge_crossings(elements) else 0,
        "color_semantics": 1 if check_color_semantics(elements) else 0,
        "node_density": 1 if check_node_density(elements) else 0,
    }


# -- Core pipeline --------------------------------------------------------------

def generate_diagram(
    bedrock: anthropic.AnthropicBedrock, prompt: str, topic: str
) -> dict | None:
    """Generate one Excalidraw JSON diagram via Claude."""
    try:
        response = bedrock.messages.create(
            model=CLAUDE_GEN_MODEL,
            max_tokens=16384,
            system=prompt,
            messages=[{
                "role": "user",
                "content": f"Create an Excalidraw diagram for: {topic}",
            }],
        )
        raw = response.content[0].text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = re.sub(r'^```\w*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)
        return json.loads(raw)
    except (json.JSONDecodeError, Exception) as exc:
        print(f"      generation ERROR: {exc}")
        return None


def generate_diagrams(
    bedrock: anthropic.AnthropicBedrock, prompt: str, run_dir: Path
) -> list[tuple[Path, dict]]:
    """Generate DIAGRAMS_PER_RUN Excalidraw files and save to run_dir."""
    run_dir.mkdir(parents=True, exist_ok=True)
    results = []
    print(f"  Generating {DIAGRAMS_PER_RUN} Excalidraw diagrams via Claude...")
    for i in range(DIAGRAMS_PER_RUN):
        topic = DIAGRAM_TOPICS[i % len(DIAGRAM_TOPICS)]
        data = generate_diagram(bedrock, prompt, topic)
        if data:
            file_path = run_dir / f"diagram_{i + 1:02d}.excalidraw"
            file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            results.append((file_path, data))
            n_elements = len(data.get("elements", []))
            print(f"    [{i + 1}/{DIAGRAMS_PER_RUN}] saved -> {file_path.name} ({n_elements} elements)")
        else:
            print(f"    [{i + 1}/{DIAGRAMS_PER_RUN}] FAILED")
    return results


def eval_diagram_claude(
    bedrock: anthropic.AnthropicBedrock, excalidraw_data: dict
) -> dict:
    """Score one diagram via Claude for subjective criteria."""
    try:
        response = bedrock.messages.create(
            model=CLAUDE_EVAL_MODEL,
            max_tokens=512,
            system=EVAL_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": f"Evaluate this Excalidraw diagram:\n\n{json.dumps(excalidraw_data, indent=2)[:8000]}",
            }],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = re.sub(r'^```\w*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)
        return json.loads(raw)
    except Exception as exc:
        print(f"      claude eval ERROR: {exc}")
        return {k: 0 for k in CRITERIA} | {"notes": str(exc)}


def eval_diagram(
    bedrock: anthropic.AnthropicBedrock, excalidraw_data: dict
) -> dict:
    """Combined eval: programmatic checks + Claude review. Uses the stricter (lower) score per criterion."""
    prog = programmatic_eval(excalidraw_data)
    claude = eval_diagram_claude(bedrock, excalidraw_data)

    # Take the minimum of both evaluators per criterion (stricter)
    scores = {}
    for key in CRITERIA:
        scores[key] = min(prog.get(key, 0), claude.get(key, 0))

    scores["notes"] = claude.get("notes", "")
    scores["prog_detail"] = prog
    scores["claude_detail"] = {k: claude.get(k, 0) for k in CRITERIA}
    return scores


def eval_batch(
    bedrock: anthropic.AnthropicBedrock,
    diagrams: list[tuple[Path, dict]],
) -> tuple[float, list[dict]]:
    """Evaluate all diagrams. Returns (total_score, per-diagram results).
    Each diagram scores 0-8 (binary per criterion), batch max = DIAGRAMS_PER_RUN * 8."""
    results = []
    total = 0.0
    max_per_diagram = len(CRITERIA)
    print(f"  Evaluating {len(diagrams)} diagrams (programmatic + Claude)...")
    for i, (path, data) in enumerate(diagrams):
        scores = eval_diagram(bedrock, data)
        diagram_score = sum(scores.get(k, 0) for k in CRITERIA)
        total += diagram_score
        results.append({**scores, "file": path.name, "score": diagram_score})
        abbrevs = " ".join(f"{k[:3]}={scores.get(k, 0)}" for k in CRITERIA)
        print(
            f"    [{i + 1}/{len(diagrams)}] {diagram_score}/{max_per_diagram}"
            f"  {abbrevs}"
            f"  -- {scores.get('notes', '')}"
        )
    return total, results


def mutate_prompt(
    bedrock: anthropic.AnthropicBedrock,
    best_prompt: str,
    eval_results: list[dict],
) -> str:
    """Ask Claude to produce an improved prompt based on weakness analysis."""
    n = len(eval_results)
    if n == 0:
        return best_prompt

    avgs = {
        k: round(sum(r.get(k, 0) for r in eval_results) / n, 2)
        for k in CRITERIA
    }
    weakest = sorted(avgs, key=avgs.get)[:3]
    sample_notes = "; ".join(r.get("notes", "") for r in eval_results[:5] if r.get("notes"))

    # Include examples of failures for context
    failures = []
    for r in eval_results:
        failed = [k for k in CRITERIA if r.get(k, 0) == 0]
        if failed:
            failures.append(f"  {r.get('file', '?')}: failed {', '.join(failed)}")
    failure_summary = "\n".join(failures[:5]) if failures else "  (none)"

    feedback = (
        f"Criterion pass rates (0-1): {json.dumps(avgs)}\n"
        f"Weakest criteria needing improvement: {', '.join(weakest)}\n"
        f"Sample evaluator notes: {sample_notes}\n"
        f"Specific failures:\n{failure_summary}"
    )

    response = bedrock.messages.create(
        model=CLAUDE_GEN_MODEL,
        max_tokens=2048,
        system=MUTATION_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f"Current prompt:\n{best_prompt}\n\n"
                f"Evaluation feedback:\n{feedback}\n\n"
                "Write the improved prompt. Keep it focused on generating valid Excalidraw JSON."
            ),
        }],
    )
    return response.content[0].text.strip()


def log_result(
    run_number: int,
    prompt: str,
    score: float,
    kept: bool,
    eval_results: list[dict],
):
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run": run_number,
        "score": score,
        "max_score": DIAGRAMS_PER_RUN * len(CRITERIA),
        "kept": kept,
        "prompt": prompt[:500],  # truncate for log readability
        "evals": eval_results,
    }
    with open(RESULTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# -- Main cycle ----------------------------------------------------------------─

def run_cycle(
    bedrock: anthropic.AnthropicBedrock,
    state: dict,
) -> dict:
    state["run_number"] += 1
    run_number = state["run_number"]
    run_dir = DIAGRAMS_DIR / f"run_{run_number:03d}"
    max_batch = DIAGRAMS_PER_RUN * len(CRITERIA)

    print(f"\n{'=' * 60}")
    print(f"Run {run_number}  |  Best so far: {state['best_score']}/{max_batch}")
    print(f"{'=' * 60}")

    prompt = load_prompt()
    print(f"  Prompt ({len(prompt)} chars): {prompt[:80]}...")

    # 1. Generate
    diagrams = generate_diagrams(bedrock, prompt, run_dir)
    if not diagrams:
        print("  No diagrams were generated -- skipping cycle.")
        save_state(state)
        return state

    # 2. Evaluate
    batch_score, eval_results = eval_batch(bedrock, diagrams)
    print(f"\n  Batch score: {batch_score}/{max_batch}  ({batch_score / max_batch * 100:.1f}%)")

    if state["baseline_score"] is None:
        state["baseline_score"] = batch_score
        print(f"  Baseline set: {batch_score}")

    # 3. Keep or discard
    kept = batch_score > state["best_score"]
    if kept:
        state["best_score"] = batch_score
        save_best_prompt(prompt)
        print(f"  >>> NEW BEST -- prompt saved as best_prompt.txt")
    else:
        print(f"  x No improvement ({batch_score} <= {state['best_score']}) -- discarding")

    # 4. Log
    log_result(run_number, prompt, batch_score, kept, eval_results)

    # 5. Mutate best prompt for next cycle
    best_prompt = load_best_prompt()
    print("  Mutating prompt for next round...")
    new_prompt = mutate_prompt(bedrock, best_prompt, eval_results)
    save_prompt(new_prompt)
    print(f"  New prompt saved ({len(new_prompt)} chars)")

    save_state(state)
    return state


def main():
    parser = argparse.ArgumentParser(description="Autoresearch Diagrams -- continuous loop")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--once", action="store_true", help="Run one cycle and exit")
    group.add_argument("--cycles", type=int, metavar="N", help="Run exactly N cycles and exit")
    args = parser.parse_args()

    ensure_dirs()
    load_prompt()  # write seed if missing

    bedrock = init_bedrock()
    state = load_state()

    if args.once:
        run_cycle(bedrock, state)

    elif args.cycles:
        for i in range(args.cycles):
            state = run_cycle(bedrock, state)
            if i < args.cycles - 1:
                print(f"\n  Sleeping {LOOP_INTERVAL_SECONDS}s...")
                time.sleep(LOOP_INTERVAL_SECONDS)

    else:
        print(f"Starting continuous loop every {LOOP_INTERVAL_SECONDS}s  (Ctrl+C to stop)")
        while True:
            state = run_cycle(bedrock, state)
            print(f"\n  Sleeping {LOOP_INTERVAL_SECONDS}s until next cycle...")
            time.sleep(LOOP_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
