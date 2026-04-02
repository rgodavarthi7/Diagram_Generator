#!/usr/bin/env python3
"""Validate an Excalidraw JSON file for quality criteria."""

import json
import re
import sys
from pathlib import Path


ALLOWED_PASTELS = {
    "#a5d8ff", "#d0bfff", "#b2f2bb", "#ffd8a8", "#fcc2d7", "#fff3bf",
}


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


def check_json_structure(data: dict) -> list[str]:
    """Verify top-level Excalidraw format."""
    errors = []
    if data.get("type") != "excalidraw":
        errors.append("Missing or wrong top-level 'type' (expected 'excalidraw')")
    if not isinstance(data.get("elements"), list):
        errors.append("Missing or invalid 'elements' array")
    if not data.get("elements"):
        errors.append("'elements' array is empty")
    return errors


def check_pastel_colors(elements: list[dict]) -> list[str]:
    """Check that all non-transparent backgroundColors are pastel."""
    errors = []
    for el in elements:
        bg = el.get("backgroundColor", "")
        if not bg or bg == "transparent":
            continue
        if bg.lower() in ALLOWED_PASTELS:
            continue
        hsl = _hex_to_hsl(bg)
        if hsl is None:
            continue
        _, s, l = hsl
        if l < 0.65:
            errors.append(f"Element '{el.get('id')}' has dark backgroundColor {bg} (lightness {l:.2f})")
        elif l < 0.75 and s > 0.7:
            errors.append(f"Element '{el.get('id')}' has vivid backgroundColor {bg}")
    return errors


def check_text_legibility(elements: list[dict]) -> list[str]:
    """Check all text elements have non-empty, reasonably short text."""
    errors = []
    text_els = [el for el in elements if el.get("type") == "text"]
    if not text_els:
        errors.append("No text elements found — diagram has no labels")
        return errors
    for el in text_els:
        text = (el.get("text", "") or "").strip()
        if not text:
            errors.append(f"Element '{el.get('id')}' has empty text")
        elif len(text) > 100:
            errors.append(f"Element '{el.get('id')}' text too long ({len(text)} chars)")
    return errors


def check_no_numbers(elements: list[dict]) -> list[str]:
    """Check that no text element contains digits or ordinals."""
    errors = []
    for el in elements:
        if el.get("type") != "text":
            continue
        text = el.get("text", "") or el.get("originalText", "")
        if re.search(r'\d', text):
            errors.append(f"Element '{el.get('id')}' contains digits: \"{text}\"")
    return errors


def check_binding_integrity(elements: list[dict]) -> list[str]:
    """Verify arrow startBinding/endBinding elementIds reference existing elements."""
    errors = []
    element_ids = {el.get("id") for el in elements if el.get("id")}
    for el in elements:
        if el.get("type") != "arrow":
            continue
        for binding_key in ("startBinding", "endBinding"):
            binding = el.get(binding_key)
            if binding and isinstance(binding, dict):
                ref_id = binding.get("elementId")
                if ref_id and ref_id not in element_ids:
                    errors.append(
                        f"Arrow '{el.get('id')}' {binding_key} references "
                        f"non-existent element '{ref_id}'"
                    )
    return errors


VALID_ELEMENT_TYPES = {"rectangle", "text", "arrow", "diamond", "ellipse"}


def check_element_types(elements: list[dict]) -> list[str]:
    """Verify all elements use known Excalidraw types."""
    errors = []
    for el in elements:
        etype = el.get("type")
        if etype not in VALID_ELEMENT_TYPES:
            errors.append(f"Element '{el.get('id')}' has unknown type '{etype}'")
    return errors


def check_container_integrity(elements: list[dict]) -> list[str]:
    """Verify text containerId and boundElements references point to existing elements."""
    errors = []
    element_ids = {el.get("id") for el in elements if el.get("id")}
    for el in elements:
        container_id = el.get("containerId")
        if container_id and container_id not in element_ids:
            errors.append(
                f"Text '{el.get('id')}' containerId references "
                f"non-existent element '{container_id}'"
            )
        for bound in (el.get("boundElements") or []):
            ref_id = bound.get("id")
            if ref_id and ref_id not in element_ids:
                errors.append(
                    f"Element '{el.get('id')}' boundElements references "
                    f"non-existent element '{ref_id}'"
                )
    return errors


def check_decision_branches(elements: list[dict]) -> list[str]:
    """Verify every diamond has at least 2 outgoing arrows."""
    errors = []
    diamonds = {el["id"] for el in elements if el.get("type") == "diamond"}
    if not diamonds:
        return errors
    arrow_sources: dict[str, list[str]] = {}
    for el in elements:
        if el.get("type") != "arrow":
            continue
        src = (el.get("startBinding") or {}).get("elementId")
        if src:
            arrow_sources.setdefault(src, []).append(el.get("id", ""))
    for d_id in diamonds:
        outgoing = arrow_sources.get(d_id, [])
        if len(outgoing) < 2:
            errors.append(
                f"Diamond '{d_id}' has {len(outgoing)} outgoing arrow(s), expected at least 2"
            )
    return errors


def validate(file_path: str) -> dict:
    """Run all checks on an Excalidraw file. Returns result dict."""
    path = Path(file_path)
    if not path.exists():
        return {"valid": False, "errors": [f"File not found: {file_path}"]}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {"valid": False, "errors": [f"Invalid JSON: {e}"]}

    all_errors = []

    # Structure check
    all_errors.extend(check_json_structure(data))
    if all_errors:
        return {"valid": False, "errors": all_errors}

    elements = data["elements"]

    # Run all checks
    checks = {
        "pastel_colors": check_pastel_colors(elements),
        "text_legibility": check_text_legibility(elements),
        "no_numbers": check_no_numbers(elements),
        "binding_integrity": check_binding_integrity(elements),
        "element_types": check_element_types(elements),
        "container_integrity": check_container_integrity(elements),
        "decision_branches": check_decision_branches(elements),
    }

    for check_errors in checks.values():
        all_errors.extend(check_errors)

    return {
        "valid": len(all_errors) == 0,
        "checks": {k: "pass" if not v else "fail" for k, v in checks.items()},
        "errors": all_errors,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <file.excalidraw>", file=sys.stderr)
        sys.exit(1)

    result = validate(sys.argv[1])
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["valid"] else 1)
