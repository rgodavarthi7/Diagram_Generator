Generate an Excalidraw diagram from the user's description. The user's idea is: $ARGUMENTS

## Workflow

1. **Parse the idea**: extract components, connections, and decision points.
2. **Choose layout mode**:
   - If the description involves decisions, conditions, branching, if/then/else, error handling, or loops → use **Flowchart Layout** (top-to-bottom)
   - Otherwise → use **Linear Layout** (left-to-right)
3. Generate valid Excalidraw JSON following the rules below.
4. Save to `data/output/{slug}-workflow.excalidraw` (slugify the description).
5. Validate by running: `python validate_diagram.py data/output/{filename}`
   - If validation fails, fix the errors and re-save.
6. Tell the user the file path, layout mode used, and what components are in the diagram.
7. Ask: "Would you like to adjust anything?"
8. On feedback: read the existing file, modify only affected elements, re-validate, save.

---

## Excalidraw JSON Format

Every diagram MUST be valid JSON with this top-level structure:
```json
{
  "type": "excalidraw",
  "version": 2,
  "source": "https://excalidraw.com",
  "elements": [...],
  "appState": {
    "gridSize": null,
    "viewBackgroundColor": "#ffffff"
  },
  "files": {}
}
```

---

## Element Templates

CRITICAL: Every element MUST include ALL fields shown below. Missing fields cause the VS Code Excalidraw extension to silently fail to render.

### Rectangle (process step)
```json
{
  "id": "rect-{name}",
  "type": "rectangle",
  "x": <calculated>, "y": <calculated>, "width": 160, "height": 80,
  "angle": 0,
  "strokeColor": "<matched stroke>",
  "backgroundColor": "<pastel>",
  "fillStyle": "solid",
  "strokeWidth": 2,
  "strokeStyle": "solid",
  "roughness": 1,
  "opacity": 100,
  "seed": <unique random integer>,
  "version": 1,
  "versionNonce": <unique integer>,
  "isDeleted": false,
  "groupIds": [],
  "boundElements": [
    {"id": "text-{name}", "type": "text"},
    {"id": "<connected arrow ids>", "type": "arrow"}
  ],
  "link": null,
  "locked": false,
  "roundness": {"type": 3}
}
```

### Diamond (decision node) — FLOWCHART ONLY
```json
{
  "id": "decision-{name}",
  "type": "diamond",
  "x": <calculated>, "y": <calculated>, "width": 140, "height": 140,
  "angle": 0,
  "strokeColor": "#f08c00",
  "backgroundColor": "#fff3bf",
  "fillStyle": "solid",
  "strokeWidth": 2,
  "strokeStyle": "solid",
  "roughness": 1,
  "opacity": 100,
  "seed": <unique random integer>,
  "version": 1,
  "versionNonce": <unique integer>,
  "isDeleted": false,
  "groupIds": [],
  "boundElements": [
    {"id": "text-{name}", "type": "text"},
    {"id": "<yes arrow id>", "type": "arrow"},
    {"id": "<no arrow id>", "type": "arrow"},
    {"id": "<incoming arrow id>", "type": "arrow"}
  ],
  "link": null,
  "locked": false,
  "roundness": {"type": 2}
}
```

### Ellipse (start/end terminal) — FLOWCHART ONLY
```json
{
  "id": "terminal-{name}",
  "type": "ellipse",
  "x": <calculated>, "y": <calculated>, "width": 120, "height": 60,
  "angle": 0,
  "strokeColor": "<matched stroke>",
  "backgroundColor": "<pastel>",
  "fillStyle": "solid",
  "strokeWidth": 2,
  "strokeStyle": "solid",
  "roughness": 1,
  "opacity": 100,
  "seed": <unique random integer>,
  "version": 1,
  "versionNonce": <unique integer>,
  "isDeleted": false,
  "groupIds": [],
  "boundElements": [
    {"id": "text-{name}", "type": "text"},
    {"id": "<connected arrow ids>", "type": "arrow"}
  ],
  "link": null,
  "locked": false,
  "roundness": null
}
```

### Text Label (inside any container: rectangle, diamond, ellipse, or arrow)
```json
{
  "id": "text-{name}",
  "type": "text",
  "x": <same as parent>, "y": <same as parent>,
  "width": <same as parent>, "height": <same as parent>,
  "angle": 0,
  "strokeColor": "#000000",
  "backgroundColor": "transparent",
  "fillStyle": "solid",
  "strokeWidth": 2,
  "strokeStyle": "solid",
  "roughness": 1,
  "opacity": 100,
  "seed": <unique random integer>,
  "version": 1,
  "versionNonce": <unique integer>,
  "isDeleted": false,
  "groupIds": [],
  "boundElements": [],
  "link": null,
  "locked": false,
  "text": "<label>",
  "fontSize": 18,
  "fontFamily": 1,
  "textAlign": "center",
  "verticalAlign": "middle",
  "containerId": "<parent element id>",
  "originalText": "<same as text>",
  "lineHeight": 1.25
}
```

Special cases for text fontSize:
- Rectangle labels: fontSize 18
- Diamond labels: fontSize 16 (less space inside diamond)
- Ellipse labels: fontSize 16
- Arrow labels: fontSize 14

### Arrow — Horizontal (linear layout)
```json
{
  "id": "arrow-{from}-to-{to}",
  "type": "arrow",
  "x": <right edge of source>, "y": <center y of source>,
  "width": 100, "height": 0,
  "angle": 0,
  "strokeColor": "<source stroke color>",
  "backgroundColor": "transparent",
  "fillStyle": "solid",
  "strokeWidth": 2,
  "strokeStyle": "solid",
  "roughness": 1,
  "opacity": 100,
  "seed": <unique random integer>,
  "version": 1,
  "versionNonce": <unique integer>,
  "isDeleted": false,
  "groupIds": [],
  "boundElements": [],
  "link": null,
  "locked": false,
  "points": [[0, 0], [100, 0]],
  "startBinding": {"elementId": "<source id>", "focus": 0, "gap": 1},
  "endBinding": {"elementId": "<target id>", "focus": 0, "gap": 1},
  "startArrowhead": null,
  "endArrowhead": "arrow"
}
```

### Arrow — Vertical (flowchart, straight down)
```json
{
  "id": "arrow-{from}-to-{to}",
  "type": "arrow",
  "x": <center x of source>,
  "y": <bottom edge of source>,
  "width": 0,
  "height": <vertical gap to target top edge>,
  "angle": 0,
  "strokeColor": "<source stroke color>",
  "backgroundColor": "transparent",
  "fillStyle": "solid",
  "strokeWidth": 2,
  "strokeStyle": "solid",
  "roughness": 1,
  "opacity": 100,
  "seed": <unique random integer>,
  "version": 1,
  "versionNonce": <unique integer>,
  "isDeleted": false,
  "groupIds": [],
  "boundElements": [],
  "link": null,
  "locked": false,
  "points": [[0, 0], [0, <gap>]],
  "startBinding": {"elementId": "<source id>", "focus": 0, "gap": 1},
  "endBinding": {"elementId": "<target id>", "focus": 0, "gap": 1},
  "startArrowhead": null,
  "endArrowhead": "arrow"
}
```

### Arrow — Bent/L-shaped (flowchart, for branches)
For a branch going right then down from a diamond:
```json
{
  "id": "arrow-{from}-to-{to}",
  "type": "arrow",
  "x": <right edge of diamond (diamond.x + diamond.width)>,
  "y": <center y of diamond (diamond.y + diamond.height/2)>,
  "width": <horizontal distance to target center>,
  "height": <vertical distance to target top>,
  "angle": 0,
  "strokeColor": "<diamond stroke color>",
  "backgroundColor": "transparent",
  "fillStyle": "solid",
  "strokeWidth": 2,
  "strokeStyle": "solid",
  "roughness": 1,
  "opacity": 100,
  "seed": <unique random integer>,
  "version": 1,
  "versionNonce": <unique integer>,
  "isDeleted": false,
  "groupIds": [],
  "boundElements": [{"id": "label-{arrow-id}", "type": "text"}],
  "link": null,
  "locked": false,
  "points": [[0, 0], [<dx>, 0], [<dx>, <dy>]],
  "startBinding": {"elementId": "<diamond id>", "focus": 0, "gap": 1},
  "endBinding": {"elementId": "<target id>", "focus": 0, "gap": 1},
  "startArrowhead": null,
  "endArrowhead": "arrow"
}
```

For a merge arrow going down then left (from side branch back to main flow):
```json
"points": [[0, 0], [0, <partial_dy>], [<negative_dx>, <total_dy>]]
```

### Arrow — Loop (flowchart, goes backward/upward)
For retry logic routing right of main flow then back up:
```json
"points": [[0, 0], [<offset_right>, 0], [<offset_right>, <negative_dy>], [0, <negative_dy>]]
```

### Arrow Label (text on decision arrows)
Arrow labels like "Yes" / "No" are text elements contained by the arrow:
```json
{
  "id": "label-{arrow-id}",
  "type": "text",
  "x": <arrow midpoint x>, "y": <arrow midpoint y>,
  "width": 40, "height": 20,
  "angle": 0,
  "strokeColor": "#000000",
  "backgroundColor": "transparent",
  "fillStyle": "solid",
  "strokeWidth": 2,
  "strokeStyle": "solid",
  "roughness": 1,
  "opacity": 100,
  "seed": <unique random integer>,
  "version": 1,
  "versionNonce": <unique integer>,
  "isDeleted": false,
  "groupIds": [],
  "boundElements": [],
  "link": null,
  "locked": false,
  "text": "Yes",
  "fontSize": 14,
  "fontFamily": 1,
  "textAlign": "center",
  "verticalAlign": "middle",
  "containerId": "<arrow id>",
  "originalText": "Yes",
  "lineHeight": 1.25
}
```
The arrow's `boundElements` must include `{"id": "label-{arrow-id}", "type": "text"}`.

---

## Color Palette — STRICT

Cycle through these. Every shape MUST use one of these pairs:

| Name | Background | Stroke |
|------|------------|--------|
| Blue | #a5d8ff | #1971c2 |
| Purple | #d0bfff | #6741d9 |
| Green | #b2f2bb | #2f9e44 |
| Orange | #ffd8a8 | #e8590c |
| Pink | #fcc2d7 | #c2255c |
| Yellow | #fff3bf | #f08c00 |

Arrow strokeColor: use the stroke color of the source element.

### Color Assignments for Flowcharts
- **Start terminal**: Blue (#a5d8ff / #1971c2)
- **End terminal**: Pink (#fcc2d7 / #c2255c)
- **Decision diamonds**: Yellow (#fff3bf / #f08c00)
- **Process rectangles**: Cycle through Purple, Green, Orange for variety
- **Error/failure rectangles**: Orange (#ffd8a8 / #e8590c)

---

## Layout Mode A: Linear (Left-to-Right)

Use this for simple sequential workflows with no branching.

- ALL rectangles at y: 200
- First box at x: 100
- Each next box: previous x + 260
- Arrows connect adjacent boxes sequentially
- Arrow x = source rect x + 160, y = 240, width = 100, height = 0

Position formula for component index i (starting at 0):
- rect x = 100 + (i * 260), y = 200
- arrow x = 100 + (i * 260) + 160, y = 240

---

## Layout Mode B: Flowchart (Top-to-Bottom)

Use this when the description involves decisions, conditions, branching, if/then/else, error handling, or retry/loop logic.

### Grid Constants
```
COLUMN_WIDTH = 300    # horizontal spacing between column centers
ROW_HEIGHT   = 200    # vertical spacing between row centers
BASE_X       = 400    # center x of column 0
BASE_Y       = 60     # top of row 0
```

### Position Formula
```
node.x = BASE_X + (col * COLUMN_WIDTH) - (node.width / 2)
node.y = BASE_Y + (row * ROW_HEIGHT)
```

Where:
- `col` = 0 for main flow, +1 for right branch, -1 for left branch
- `row` = sequential row number starting at 0

### Element sizes
- Rectangle: 160 x 80
- Diamond: 140 x 140
- Ellipse: 120 x 60

### Vertical Arrow Math (same column, adjacent rows)
```
arrow.x = BASE_X + (col * COLUMN_WIDTH)
arrow.y = source.y + source.height
gap = (BASE_Y + target_row * ROW_HEIGHT) - (source.y + source.height)
arrow.height = gap
arrow.points = [[0, 0], [0, gap]]
```

### Bent Arrow Math (diamond to side branch)
Right branch (col 0 → col +1):
```
arrow.x = diamond.x + diamond.width
arrow.y = diamond.y + diamond.height / 2
dx = COLUMN_WIDTH - diamond.width/2 + target.width/2
dy = ROW_HEIGHT - diamond.height/2 + target.height/2
arrow.points = [[0, 0], [dx, 0], [dx, dy]]
```

Left branch (col 0 → col -1): same but dx is negative.

### Merge Arrow Math (side branch back to main flow End)
```
arrow.x = side_node.x + side_node.width / 2
arrow.y = side_node.y + side_node.height
dx = (BASE_X - side_node.x - side_node.width/2)
dy = (end_node.y - side_node.y - side_node.height)
arrow.points = [[0, 0], [0, dy/2], [dx, dy]]
```

### Flowchart Conventions
1. **Primary/happy path** flows straight down in column 0
2. **Decision "Yes"** always goes DOWN (continues main flow)
3. **Decision "No"** goes RIGHT to column +1 (or LEFT to column -1 for variety)
4. **Every diamond** must have exactly 2 outgoing arrows with labels ("Yes" / "No")
5. **Branches merge** back to a single End terminal at the bottom via bent arrows
6. **Start** is always row 0, **End** is always the last row
7. **Loop/retry arrows** route along the outside (right edge) and arc back up using 4-point paths

### Example: API Request Lifecycle with Auth + Rate Limiting

```
Row 0, Col  0:  terminal-start     (ellipse, blue)
Row 1, Col  0:  rect-receive       (rect, purple)
Row 2, Col  0:  decision-auth      (diamond, yellow)
Row 3, Col  0:  rect-parse         (rect, green)          ← Yes
Row 3, Col +1:  rect-unauth        (rect, orange)         ← No
Row 4, Col  0:  decision-rate      (diamond, yellow)
Row 5, Col  0:  rect-route         (rect, purple)         ← No
Row 5, Col -1:  rect-too-many      (rect, orange)         ← Yes
Row 6, Col  0:  rect-response      (rect, green)
Row 7, Col  0:  terminal-end       (ellipse, pink)

Arrows:
  start → receive         (vertical)
  receive → auth          (vertical)
  auth → parse            (vertical, label "Yes")
  auth → unauth           (bent right, label "No")
  parse → rate            (vertical)
  rate → route            (vertical, label "No")
  rate → too-many         (bent left, label "Yes")
  route → response        (vertical)
  response → end          (vertical)
  unauth → end            (merge: down then left)
  too-many → end          (merge: down then right)
```

---

## Text Rules — CRITICAL

- Node labels: 1-3 words max, letters and spaces only
- Diamond labels: 1-2 words (less space inside diamond)
- Arrow labels: single word — "Yes", "No", "Error", "Retry"
- **ZERO digits** anywhere — no "Step 1", "v2", "Phase 3"

---

## Handling Feedback

When user gives feedback:
1. Read the current .excalidraw file
2. Apply the change:
   - **Add a node**: Insert new shape + text + arrows, shift rows if needed
   - **Remove a node**: Delete shape + text + connected arrows, reconnect flow
   - **Add a decision**: Insert diamond + two branches + labels, shift downstream rows
   - **Add a loop**: Create 4-point arrow routing outside the main flow back up
   - **Rename**: Update text element's `text` and `originalText`
   - **Change colors**: Swap backgroundColor and strokeColor pair
3. Re-validate with `python validate_diagram.py <path>`
4. Save (overwrite same file, or new version if user asks)
