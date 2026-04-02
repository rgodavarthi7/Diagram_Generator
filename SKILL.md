---
name: autoresearch-diagrams
description: Self-improving diagram prompt optimization inspired by the Karpathy autoresearch pattern (https://github.com/karpathy/autoresearch — the concept, not the library). Generates batches of diagrams via Amazon Nova Canvas on AWS Bedrock, evaluates via Claude Sonnet vision on Bedrock using the Anthropic SDK's AnthropicBedrock client, mutates the prompt, keeps winners. Includes a live web dashboard.
allowed-tools: Read, Bash, Glob, Grep
---

# Autoresearch Diagrams — Self-Improving Prompt Optimization

> **Pattern source**: [karpathy/autoresearch](https://github.com/karpathy/autoresearch) — that repo is about autonomous LLM training on GPUs and is not used directly here. We borrow only the core loop concept: generate → evaluate → keep/discard → mutate → repeat.

## What It Does
Applies the Karpathy autoresearch pattern to diagram generation prompts. Every 2 minutes:
1. Generates 10 diagrams with the current prompt (Amazon Nova Canvas via AWS Bedrock)
2. Evaluates each against 4 criteria via Claude Sonnet vision (score out of 40)
3. Keeps the prompt if it beats the best score, discards otherwise
4. Mutates the best prompt to try to improve further
5. Logs everything to JSONL for tracking

## Eval Criteria (4 per image, 40 max per batch)
1. **Legible & grammatical** — all text readable, correctly spelled
2. **Pastel colors** — soft pastel fills only, no saturated/dark colors
3. **Linear layout** — strictly left-to-right or top-to-bottom
4. **No numbers** — zero digits, ordinals, or step numbers

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run continuous loop (every 2 min)
python autoresearch.py

# Single cycle (test)
python autoresearch.py --once

# Run N cycles
python autoresearch.py --cycles 10

# Start the live dashboard (separate terminal)
python dashboard.py --port 8501
# Then open http://localhost:8501
```

## Environment
Requires in `.env`:
```
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
AWS_DEFAULT_REGION=us-east-1
```

Dependencies:
- `boto3` — Nova Canvas image generation
- `anthropic[bedrock]` — Claude eval + mutation via `AnthropicBedrock` client
- `python-dotenv`

## File Structure

```
autoresearch.py       # Main generate -> eval -> mutate loop
dashboard.py          # Live web dashboard (Chart.js)
requirements.txt      # Python dependencies
SKILL.md              # This file
.env                  # API keys (not committed)
data/
  prompt.txt          # Current prompt being optimized
  best_prompt.txt     # Best prompt found so far
  state.json          # Loop state (run number, best score)
  results.jsonl       # Append-only experiment log
  diagrams/
    run_001/          # 10 diagrams per run
    run_002/
    ...
```

## Models
- **Generation**: `amazon.nova-canvas-v1:0` (Nova Canvas via `boto3` bedrock-runtime)
- **Evaluation**: `anthropic.claude-sonnet-4-5-20251001-v1:0` (Claude via `AnthropicBedrock` SDK — vision + structured JSON output)
- **Mutation**: `anthropic.claude-sonnet-4-5-20251001-v1:0` (Claude via `AnthropicBedrock` SDK — prompt rewriting based on failure analysis)

## Dashboard
Serves at `http://localhost:8501` with:
- 4 stat cards (current best, baseline, improvement %, runs/kept)
- Score-over-time chart with keep/discard dot coloring
- Per-criterion breakdown charts (legible, pastel, linear, no numbers)
- Run history table
- Current best prompt display
- Auto-refreshes every 15s

## Cost
- ~$0.04-0.06 per diagram generation (Nova Canvas on Bedrock)
- ~$0.01 per eval (Claude Sonnet vision on Bedrock, small image + short response)
- ~$0.01 per mutation (Claude Sonnet text on Bedrock)
- **Total: ~$0.50-0.70 per cycle (10 diagrams)**
- At 2-min intervals: ~$15-21/hour
