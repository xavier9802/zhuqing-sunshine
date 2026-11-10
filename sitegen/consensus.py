from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from sitegen.build import write_json

CONDITION_LABELS = {
    "sunny": "晴",
    "mostly_sunny": "晴间多云",
    "partly_cloudy": "多云间晴",
    "variable": "天气变化",
    "cloudy": "多云/阴",
    "overcast": "阴",
    "rainy": "有降水",
    "pending": "待更新",
}
CONDITION_RANK = {
    "sunny": 6,
    "mostly_sunny": 5,
    "partly_cloudy": 4,
    "variable": 3,
    "cloudy": 2,
    "overcast": 1,
    "rainy": 0,
}


def build_consensus(output: Path, model_statuses: list[dict[str, Any]], generated_at: str) -> dict[str, Any]:
    available = [item for item in model_statuses if item.get("status") == "available"]
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for model in available:
        path = output / "data" / "overview" / f"{model['model_id']}.json"
        if not path.is_file():
            continue
        import json
        payload = json.loads(path.read_text(encoding="utf-8"))
        for day in payload.get("daily_sunshine_hours", []):
            if day.get("condition") and day["condition"] != "pending":
                by_date[day["date"]].append({
                    **day,
                    "model_id": model["model_id"],
                    "model_name": model["model_name"],
                })

    daily: list[dict[str, Any]] = []
    for day, rows in sorted(by_date.items()):
        votes = Counter(row["condition"] for row in rows)
        ordered = votes.most_common()
        top_count = ordered[0][1] if ordered else 0
        tied = len(ordered) > 1 and ordered[1][1] == top_count
        condition = ordered[0][0] if ordered and not tied else "variable"
        def avg(field: str) -> float | None:
            values = [float(row[field]) for row in rows if row.get(field) is not None]
            return round(sum(values) / len(values), 1) if values else None
        agreement = round(top_count / len(rows) * 100) if rows else 0
        daily.append({
            "date": day,
            "condition": condition,
            "condition_label": CONDITION_LABELS.get(condition, "天气变化"),
            "model_count": len(rows),
            "agreement_count": top_count,
            "agreement_pct": agreement,
            "agreement_label": f"{top_count}/{len(rows)} 个模型同类判断" if rows else "无有效模型",
            "sunshine_hours": avg("sunshine_hours"),
            "mean_cloud_cover_pct": avg("mean_cloud_cover_pct"),
            "mean_low_cloud_cover_pct": avg("mean_low_cloud_cover_pct"),
            "mean_clear_sky_coverage_pct": avg("mean_clear_sky_coverage_pct"),
            "mean_bright_sky_coverage_pct": avg("mean_bright_sky_coverage_pct"),
            "sunny_score": avg("sunny_score"),
            "clear_hours": round(avg("clear_hours") or 0),
            "bright_hours": round(avg("bright_hours") or 0),
            "rain_hours": round(avg("rain_hours") or 0),
            "models": [row["model_id"] for row in rows],
        })

    eligible = [
        row for row in daily
        if row["model_count"] >= 2 and row["condition"] in {"sunny", "mostly_sunny", "partly_cloudy"}
    ]
    best = max(
        eligible,
        key=lambda row: (
            CONDITION_RANK.get(row["condition"], 0),
            row["sunny_score"] if row["sunny_score"] is not None else -1,
            row["agreement_pct"],
        ),
        default=None,
    )
    payload = {
        "status": "available" if len(available) >= 2 else "limited",
        "generated_at": generated_at,
        "model_count": len(available),
        "daily": daily,
        "best_sunny_day": best,
        "method": {
            "version": "1.1",
            "model_voting": "等权分类投票；不把相关模型视为独立概率样本",
            "sunny_score": "基于晴空覆盖、明亮覆盖、低云、总云和降水的透明规则指数，不是晴天概率",
            "minimum_models_for_recommendation": 2,
            "note": "三个模型均来自 ECMWF 预报体系，模型一致性仅作方向参考，尚未通过地面观测校准。",
        },
    }
    write_json(output / "data" / "consensus.json", payload)
    return payload
