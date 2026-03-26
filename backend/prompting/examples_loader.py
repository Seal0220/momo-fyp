from __future__ import annotations

import csv
from pathlib import Path


def _read_csv(path: str) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_tracking_examples(paths: list[str]) -> dict[int, list[dict[str, str]]]:
    stage_map: dict[int, list[dict[str, str]]] = {index: [] for index in range(1, 11)}
    for path in paths:
        for row in _read_csv(path):
            order = row.get("順序") or row.get("階段")
            if order and order.isdigit():
                stage_map[int(order)].append(
                    {
                        "source": path,
                        "stage_index": order,
                        "event_hint": row.get("觀測到動作/特徵") or row.get("語氣重點") or "",
                        "example_text": row.get("AI 產出文本 (漢尼拔口吻，20 字內)")
                        or row.get("文本範例 (符合 5 秒朗讀，親切且不安，以「高瘦、黑衣、手抖」為例)")
                        or "",
                    }
                )
            elif row.get("階段") == "重獲":
                stage_map[0] = stage_map.get(0, []) + [
                    {
                        "source": path,
                        "stage_index": "reacquire",
                        "event_hint": row.get("觀測到動作/特徵", ""),
                        "example_text": row.get("AI 產出文本 (漢尼拔口吻，20 字內)", ""),
                    }
                ]
    return stage_map


def load_idle_examples(paths: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in paths:
        rows.extend(_read_csv(path))
    return rows

