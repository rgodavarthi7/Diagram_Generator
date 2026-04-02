# Autoresearch Diagrams

Self-improving prompt optimization for Excalidraw diagram generation, inspired by [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) pattern.

Instead of manually tweaking prompts, this system runs an automated loop: **generate -> evaluate -> keep/discard -> mutate -> repeat**. Each cycle produces a batch of diagrams, scores them against binary eval criteria, and evolves the prompt to fix weaknesses.

## How It Works

### The Core Loop

```
                +------------+
                |  Load      |
                |  Prompt    |
                +-----+------+
                      |
                      v
              +-------+--------+
              |  Generate 10   |
              |  Excalidraw    |  Claude Sonnet 4.6 on Bedrock
              |  JSON diagrams |
              +-------+--------+
                      |
                      v
              +-------+--------+
              |  Evaluate each |  Programmatic checks (colors, layout,
              |  against 4     |  numbers) + Claude Haiku 4.5 vision
              |  binary evals  |  eval. Strictest score wins.
              +-------+--------+
                      |
                      v
              +-------+--------+
              |  Score > Best? |
              |  YES: keep     |
              |  NO: discard   |
              +-------+--------+
                      |
                      v
              +-------+--------+
              |  Mutate prompt |  Claude Sonnet analyzes failures,
              |  based on      |  rewrites prompt to fix weaknesses
              |  weaknesses    |
              +-------+--------+
                      |
                      v
                 (next cycle)
```

### Eval Criteria (4 binary checks per diagram, 40 max per batch)

Each diagram is scored pass/fail on these 4 criteria:

| Criterion | What It Checks | How |
|-----------|---------------|-----|
| **Legible** | All text is readable, non-empty, correctly spelled | Programmatic (non-empty, reasonable length) + Claude review |
| **Pastel** | Background colors are soft pastels, no dark/vivid fills | Programmatic (HSL lightness check against allowed palette) |
| **Linear** | Layout flows left-to-right or top-to-bottom | Programmatic (x/y variance analysis of shape centers) |
| **No Numbers** | Zero digits, ordinals, or step labels in any text | Programmatic (regex scan) + Claude review |

**Scoring**: 10 diagrams x 4 criteria = **40 points max** per run. A score of 37/40 means 92.5% of checks passed.

### Dual Evaluation

Every diagram gets evaluated twice:
1. **Programmatic** -- deterministic code checks (color hex values, coordinate analysis, regex)
2. **Claude Haiku** -- LLM review for subjective quality (spelling, readability, layout judgment)

The **stricter** (lower) score per criterion is used. This prevents the LLM from being too lenient.

### Prompt Mutation

After each batch, Claude Sonnet analyzes which criteria scored lowest across all 10 diagrams, then rewrites the prompt to strengthen those areas. The mutated prompt is used for the next cycle. If it scores higher, it becomes the new best; if not, the system falls back to the previous best.

## Results

Starting from a basic seed prompt, the system achieved:

| Run | Score | Improvement |
|-----|-------|-------------|
| 1 (baseline) | 26/40 (65%) | -- |
| 2 | 29/40 (72%) | +11.5% |
| 8 | 37/40 (92.5%) | +42.3% |

The evolved prompt added explicit color pairing rules, a verification checklist, and character-by-character number scanning -- improvements a human might not think to add.

## File Structure

```
autoresearch.py       # Main generate -> eval -> mutate loop
dashboard.py          # Live web dashboard (Chart.js, auto-refreshes)
requirements.txt      # Python dependencies
SKILL.md              # Claude Code skill definition
README.md             # This file
.env                  # AWS region config (credentials via SSO)
data/
  prompt.txt          # Current prompt being optimized
  best_prompt.txt     # Best prompt found so far
  state.json          # Loop state (run number, best score)
  results.jsonl       # Append-only experiment log
  diagrams/
    run_001/          # 10 .excalidraw files per run
    run_002/
    ...
```

## Setup

### Prerequisites

- Python 3.11+
- AWS Bedrock access with Claude Sonnet 4.6 and Haiku 4.5 enabled
- AWS SSO session active (`aws sso login`)

### Install

```bash
pip install -r requirements.txt
```

### Configure

The `.env` file only needs your AWS region. Credentials are picked up from your active SSO session:

```
AWS_DEFAULT_REGION=us-east-1
```

## Usage

### Run a single test cycle

```bash
python autoresearch.py --once
```

### Run N cycles

```bash
python autoresearch.py --cycles 10
```

### Run continuous loop (every 2 minutes)

```bash
python autoresearch.py
```

### Start the live dashboard

In a separate terminal:

```bash
python dashboard.py --port 8501
```

Then open http://localhost:8501. The dashboard shows:
- Best score, baseline, improvement %, and run count
- Score-per-run bar chart (green = kept, red = discarded)
- Radar chart of latest run's per-criterion breakdown
- Per-criterion trend lines (last 30 runs)
- Run history table
- Current best prompt text

Auto-refreshes every 15 seconds.

### View generated diagrams

The `.excalidraw` files in `data/diagrams/run_XXX/` can be opened directly in [excalidraw.com](https://excalidraw.com) -- just drag and drop.

## Adapting This for Your Other Skills

The autoresearch pattern works for **any skill with measurable output**. Here's how to apply it to a different skill:

### Step 1: Define Your Eval Criteria

Write 3-6 **binary** (yes/no) criteria. Keep them simple and objective. Avoid scales (1-10) -- binary is more reliable because it reduces compounding variability.

**Good evals:**
- "Does the output contain a summary section?" (yes/no)
- "Is every link in the output a valid URL format?" (yes/no)
- "Is the response under 500 words?" (yes/no)

**Bad evals:**
- "Rate the quality from 1-10" (too subjective, high variance)
- "Does it feel professional?" (not measurable)

### Step 2: Write Programmatic Checks Where Possible

For each criterion, ask: "Can I check this with code?"

- Word count -> `len(text.split())`
- Contains required sections -> regex or string search
- Valid JSON/YAML -> `json.loads()` / `yaml.safe_load()`
- No forbidden words -> regex scan
- Correct format -> pattern matching

Programmatic checks are deterministic and free. Use Claude eval only for subjective criteria (tone, accuracy, readability).

### Step 3: Create Your Seed Prompt

Write a basic version of your skill's prompt. It doesn't need to be great -- the loop will improve it. Include the core task description and any hard constraints.

### Step 4: Define Test Inputs

Create a list of 5-10 representative inputs your skill should handle. These get cycled through during generation. Variety matters -- include easy and hard cases.

### Step 5: Adapt the Code

Copy `autoresearch.py` and modify these sections:

1. **`DIAGRAM_TOPICS`** -> Your test inputs
2. **`SEED_PROMPT`** -> Your skill's initial prompt
3. **`EVAL_SYSTEM_PROMPT`** -> Your eval criteria for Claude
4. **`programmatic_eval()`** -> Your code-based checks
5. **`generate_diagram()`** -> Change to call your skill and return its output
6. **`eval_diagram_claude()`** -> Adjust the input format sent to Claude for review

### Step 6: Run and Watch

```bash
# Terminal 1: dashboard
python dashboard.py --port 8501

# Terminal 2: autoresearch loop
python autoresearch.py --cycles 20
```

Watch the dashboard. If a criterion stays flat at 0, your check might be too strict (like our pastel bug). If everything maxes out quickly, add harder criteria.

### Tips

- **Start with 3-4 evals**, add more once the basics are solid
- **Run at least 10 cycles** before judging -- early runs are noisy
- **Check the best_prompt.txt** after optimization -- the mutations often reveal prompt engineering tricks you wouldn't think of
- **Binary evals only** -- scales (1-10) compound variance and make scores unreliable
- **Cost awareness**: each cycle costs ~$0.30-0.50 on Bedrock (10 generations + 10 evals + 1 mutation). Budget ~$5-15 for a full optimization session
- **Save your results.jsonl** -- it's a record of every experiment. You can feed this history to a future, smarter model to continue optimization

### Example: Adapting for a Proposal Generator Skill

```python
PROPOSAL_TOPICS = [
    "Build a customer portal for a mid-size insurance company",
    "Migrate legacy mainframe to cloud microservices",
    "Implement real-time fraud detection for payment processing",
]

EVAL_CRITERIA = {
    "has_executive_summary": "Does the proposal start with an executive summary section?",
    "has_timeline": "Does the proposal include a project timeline or milestones?",
    "no_jargon": "Is the proposal free of unexplained technical jargon?",
    "under_800_words": "Is the proposal under 800 words?",
    "has_cost_section": "Does the proposal include a cost or pricing section?",
}
```

Then write programmatic checks for what you can (word count, section headers via regex) and let Claude judge the rest (jargon, readability).
