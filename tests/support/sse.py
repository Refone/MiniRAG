"""SSE 帧解析（TestClient 文本流 -> event/data 列表）。"""

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class SseFrame:
    event: str
    data: dict


def parse_sse(text: str) -> list[SseFrame]:
    frames: list[SseFrame] = []
    event: str | None = None
    data_lines: list[str] = []

    for line in text.splitlines():
        if line.startswith("event: "):
            event = line.removeprefix("event: ")
        elif line.startswith("data: "):
            data_lines.append(line.removeprefix("data: "))
        elif line == "" and event is not None:
            raw = "\n".join(data_lines) or "{}"
            frames.append(SseFrame(event=event, data=json.loads(raw)))
            event = None
            data_lines = []

    return frames
