"""Strip swimlane frames and their 01/02 labels from a delivered Archify HTML,
and optionally draw a dashed subgraph boundary around a set of nodes."""

import re
import sys
from pathlib import Path

LANE_RECT = re.compile(
    r'\n?\s*<rect data-graph-role="structural-frame" '
    r'data-composition-frame-kind="lane" '
    r'data-composition-frame-id="lane-\d+"[^>]*/>'
)

LANE_LABEL = re.compile(
    r'\n?\s*<text x="\d+(?:\.\d+)?" y="\d+(?:\.\d+)?" class="t-dim" '
    r'font-size="10" font-weight="600">\d\d / [^<]*</text>'
)


def node_rect(html: str, node_id: str) -> tuple[float, float, float, float]:
    start = html.find(f'<g id="node-{node_id}"')
    if start < 0:
        raise ValueError(f"node not found: {node_id}")
    rect_start = html.find("<rect", start)
    rect_end = html.find("/>", rect_start) + 2
    attrs = dict(re.findall(r'(\w+)="([^"]*)"', html[rect_start:rect_end]))
    return (
        float(attrs["x"]),
        float(attrs["y"]),
        float(attrs["width"]),
        float(attrs["height"]),
    )


def add_boundary(
    html: str,
    node_ids: list[str],
    label: str,
    pad_x: float = 16,
    pad_top: float = 30,
    pad_bottom: float = 12,
) -> str:
    rects = [node_rect(html, node_id) for node_id in node_ids]
    left = min(rect[0] for rect in rects)
    top = min(rect[1] for rect in rects)
    right = max(rect[0] + rect[2] for rect in rects)
    bottom = max(rect[1] + rect[3] for rect in rects)
    x = round(left - pad_x, 1)
    y = round(top - pad_top, 1)
    width = round(right - left + pad_x * 2, 1)
    height = round(bottom - top + pad_top + pad_bottom, 1)
    markup = (
        f'        <rect data-graph-role="structural-frame" '
        f'data-composition-frame-kind="group" data-composition-frame-id="group-md-tail" '
        f'x="{x}" y="{y}" width="{width}" height="{height}" rx="9" '
        f'class="c-lane" stroke-width="1"/>\n'
        f'        <text x="{x + 12}" y="{y + 15}" class="t-muted" '
        f'font-size="8" font-weight="600">{label}</text>\n'
    )
    if 'data-composition-frame-id="group-md-tail"' in html:
        return html
    marker = "<!-- Workflow groups -->"
    index = html.index(marker) + len(marker)
    return html[:index] + "\n" + markup + html[index:]


def svg_content_bounds(svg: str) -> tuple[float, float, float, float]:
    xs: list[float] = []
    ys: list[float] = []
    for tag in re.findall(r"<rect\b[^>]*>", svg):
        attrs = dict(re.findall(r'([\w:-]+)="([^"]*)"', tag))
        if not {"x", "y", "width", "height"} <= set(attrs):
            continue
        try:
            x = float(attrs["x"])
            y = float(attrs["y"])
            width = float(attrs["width"])
            height = float(attrs["height"])
        except ValueError:
            continue
        xs.extend([x, x + width])
        ys.extend([y, y + height])
    for tag in re.findall(r"<path\b[^>]*>", svg):
        attrs = dict(re.findall(r'([\w:-]+)="([^"]*)"', tag))
        if "data-edge-from" not in attrs:
            continue
        numbers = re.findall(r"-?\d+(?:\.\d+)?", attrs.get("d", ""))
        coords = [float(number) for number in numbers]
        xs.extend(coords[0::2])
        ys.extend(coords[1::2])
    return min(xs), min(ys), max(xs), max(ys)


def crop_viewbox(html: str, pad: float = 24) -> tuple[str, str]:
    start = html.find("<svg")
    end = html.find("</svg>", start) + len("</svg>")
    svg = html[start:end]
    left, top, right, bottom = svg_content_bounds(svg)
    x = round(left - pad, 1)
    y = round(top - pad, 1)
    width = round(right - left + pad * 2, 1)
    height = round(bottom - top + pad * 2, 1)
    updated = re.sub(
        r'viewBox="[^"]*"', f'viewBox="{x} {y} {width} {height}"', svg, count=1
    )
    updated = re.sub(
        r'<rect width="100%" height="100%" fill="url\(#grid\)"\s*/>',
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" fill="url(#grid)"/>',
        updated,
    )
    return html[:start] + updated + html[end:], f"{x} {y} {width} {height}"


def run(path: Path, boundary: tuple[list[str], str] | None, crop: bool = False) -> dict:
    html = path.read_text(encoding="utf-8")
    removed = len(LANE_RECT.findall(html))
    labels = len(LANE_LABEL.findall(html))
    html = LANE_RECT.sub("", html)
    html = LANE_LABEL.sub("", html)
    if boundary:
        html = add_boundary(html, boundary[0], boundary[1])
    result = {
        "removed_lanes": removed,
        "removed_lane_labels": labels,
    }
    if crop:
        html, view_box = crop_viewbox(html)
        result["viewBox"] = view_box
    path.write_text(html, encoding="utf-8")
    result["bytes"] = path.stat().st_size
    return result


if __name__ == "__main__":
    target = Path(sys.argv[1])
    crop = "--crop" in sys.argv
    if len(sys.argv) > 2 and sys.argv[2] == "--boundary":
        ids = sys.argv[3].split(",")
        label = sys.argv[4]
        print(run(target, (ids, label), crop))
    else:
        print(run(target, None, crop))
