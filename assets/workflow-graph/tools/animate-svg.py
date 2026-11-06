"""Add a flowing-arrow animation layer to an Archify canonical SVG export."""

import math
import sys
from pathlib import Path

from lxml import etree

SVG = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"

FLOW_CSS = """
:root, svg { --flow-default: #e2e8f0; --flow-emphasis: #d1fae5; }
@media (prefers-color-scheme: light) { :root, svg { --flow-default: #475569; --flow-emphasis: #6ee7b7; } }
svg[data-theme="dark"] { --flow-default: #e2e8f0; --flow-emphasis: #d1fae5; }
svg[data-theme="light"] { --flow-default: #475569; --flow-emphasis: #6ee7b7; }
.flow-line { fill: none; stroke-linecap: round; stroke-dasharray: 4 13; pointer-events: none; animation: archify-flow-dash 0.95s linear infinite; }
.flow-line.a-default { stroke: var(--flow-default); stroke-width: 1.6; }
.flow-line.a-emphasis { stroke: var(--flow-emphasis); stroke-width: 2; }
.flow-line.a-security, .flow-line.a-dashed { stroke: var(--flow-default); stroke-width: 1.6; }
.flow-chevron-mark { fill: none; stroke-width: 1.9; stroke-linecap: round; stroke-linejoin: round; }
.flow-chevron-mark.a-default { stroke: var(--flow-default); }
.flow-chevron-mark.a-emphasis { stroke: var(--flow-emphasis); }
.flow-chevron { filter: drop-shadow(0 0 2.5px var(--flow-emphasis)); }
@keyframes archify-flow-dash { from { stroke-dashoffset: 0; } to { stroke-dashoffset: -17; } }
"""


def parse_points(d: str) -> list[tuple[float, float]]:
    tokens = d.replace(",", " ").split()
    points: list[tuple[float, float]] = []
    current = (0.0, 0.0)
    i = 0
    cmd = "M"
    while i < len(tokens):
        token = tokens[i]
        if token.isalpha():
            cmd = token
            i += 1
            continue
        if cmd in ("M", "L"):
            current = (float(tokens[i]), float(tokens[i + 1]))
            points.append(current)
            i += 2
        elif cmd in ("H", "V"):
            value = float(token)
            if cmd == "H":
                current = (value, current[1])
            else:
                current = (current[0], value)
            points.append(current)
            i += 1
        else:
            i += 1
    return points


def polyline_length(points: list[tuple[float, float]]) -> float:
    return sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(points, points[1:]))


def trim_polyline(
    points: list[tuple[float, float]], head: float, tail: float
) -> list[tuple[float, float]]:
    """Return the polyline between `head` and `length - tail` along the path."""
    total = polyline_length(points)
    if len(points) < 2:
        return points
    if total <= head + tail + 12:
        return points
    start_d = head
    end_d = total - tail

    def lerp(a, b, ratio):
        return (a[0] + (b[0] - a[0]) * ratio, a[1] + (b[1] - a[1]) * ratio)

    out: list[tuple[float, float]] = []
    acc = 0.0
    for a, b in zip(points, points[1:]):
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        if acc + seg >= start_d:
            out.append(lerp(a, b, (start_d - acc) / seg if seg else 0.0))
            break
        acc += seg

    acc = 0.0
    for a, b in zip(points, points[1:]):
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        acc += seg
        if start_d < acc < end_d:
            out.append(b)

    acc = 0.0
    for a, b in zip(points, points[1:]):
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        if acc + seg >= end_d:
            out.append(lerp(a, b, (end_d - acc) / seg if seg else 0.0))
            break
        acc += seg

    return out


def to_path(points: list[tuple[float, float]]) -> str:
    if len(points) < 2:
        return ""
    body = " ".join(f"L {x:.2f} {y:.2f}" for x, y in points[1:])
    return f"M {points[0][0]:.2f} {points[0][1]:.2f} {body}"


def animate(src: Path, dst: Path) -> dict:
    etree.register_namespace("xlink", XLINK)
    tree = etree.parse(str(src))
    root = tree.getroot()

    style = root.find(f"{{{SVG}}}style")
    if style is None:
        style = etree.Element(f"{{{SVG}}}style")
        root.insert(0, style)
    style.text = (style.text or "") + FLOW_CSS

    view_box = (root.get("viewBox") or "0 0 0 0").split()
    bx, by, bw, bh = (float(value) for value in view_box)
    if bw > 0 and bh > 0:
        target_width = 1340.0
        root.set("width", f"{target_width:g}")
        root.set("height", f"{target_width * bh / bw:.1f}")
    for rect in root.iter(f"{{{SVG}}}rect"):
        if rect.get("width") == "100%" or rect.get("height") == "100%":
            rect.set("x", f"{bx:g}")
            rect.set("y", f"{by:g}")
            rect.set("width", f"{bw:g}")
            rect.set("height", f"{bh:g}")

    defs = root.find(f"{{{SVG}}}defs")
    if defs is None:
        defs = etree.Element(f"{{{SVG}}}defs")
        root.insert(1, defs)

    edge_paths = [el for el in root.iter(f"{{{SVG}}}path") if el.get("data-edge-id")]

    for index, edge in enumerate(edge_paths):
        d = edge.get("d") or ""
        classes = (edge.get("class") or "").split()
        variant = next((c for c in classes if c.startswith("a-")), "a-default")
        points = parse_points(d)
        length = polyline_length(points)
        duration = max(1.4, min(5.5, round(length / 120.0, 2)))
        begin = round(-(index * 0.62), 2)

        motion_points = trim_polyline(
            points, min(10, length * 0.2), min(14, length * 0.25)
        )
        motion_path = etree.SubElement(defs, f"{{{SVG}}}path")
        motion_path.set("id", f"flow-motion-{index}")
        motion_path.set("d", to_path(motion_points))
        motion_path.set("fill", "none")
        motion_path.set("stroke", "none")

        overlay = etree.Element(f"{{{SVG}}}path")
        overlay.set("d", d)
        overlay.set("class", "flow-line " + variant)
        overlay.set("id", f"flow-path-{index}")
        edge.addnext(overlay)

        if length < 64:
            # too short for a travelling arrow: the dash flow alone carries direction
            continue

        chevron = etree.Element(f"{{{SVG}}}g")
        chevron.set("class", "flow-chevron")
        chevron.set("opacity", "0")

        fade = etree.SubElement(chevron, f"{{{SVG}}}animate")
        fade.set("attributeName", "opacity")
        fade.set("values", "0;0.95;0.95;0")
        fade.set("keyTimes", "0;0.12;0.86;1")
        fade.set("dur", f"{duration}s")
        fade.set("begin", f"{begin}s")
        fade.set("repeatCount", "indefinite")
        fade.set("calcMode", "linear")

        mark = etree.SubElement(chevron, f"{{{SVG}}}path")
        mark.set("d", "M -5.2 -3.8 L 3 0 L -5.2 3.8")
        mark.set("class", "flow-chevron-mark " + variant)

        motion = etree.SubElement(chevron, f"{{{SVG}}}animateMotion")
        motion.set("dur", f"{duration}s")
        motion.set("begin", f"{begin}s")
        motion.set("repeatCount", "indefinite")
        motion.set("rotate", "auto")
        mpath = etree.SubElement(motion, f"{{{SVG}}}mpath")
        mpath.set("href", f"#flow-motion-{index}")
        mpath.set(f"{{{XLINK}}}href", f"#flow-motion-{index}")

        overlay.addnext(chevron)

    tree.write(str(dst), xml_declaration=True, encoding="utf-8", pretty_print=False)
    return {"edges": len(edge_paths), "bytes": dst.stat().st_size}


if __name__ == "__main__":
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    print(animate(src, dst))
