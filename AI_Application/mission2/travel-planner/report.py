"""결과 저장 — 원본 JSON · 최종 리포트 Markdown · 대체 리포트."""

import json
import os


def raw_path(results_dir, date):
    return os.path.join(results_dir, f"{date}_raw.json")


def report_path(results_dir, date):
    return os.path.join(results_dir, f"{date}_travel_plan.md")


def save_raw(path, raw):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)


def load_raw(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_report(path, markdown):
    with open(path, "w", encoding="utf-8") as f:
        f.write(markdown.rstrip() + "\n")


def errors_section(errors):
    """리포트 끝에 붙는 오류 요약 섹션. 오류가 없어도 섹션은 둔다."""
    lines = ["## 오류 요약(errors)", ""]
    if not errors:
        lines.append("- 없음")
    for e in errors:
        lines.append(f"- `{e['step']}` · `{e['type']}` — {e['message']}")
    return "\n".join(lines)


def _places_lines(places):
    if not places:
        return ["- 데이터 없음 (장소 검색 결과 0건)"]
    lines = []
    for p in places:
        title = f"[{p['name']}]({p['url']})" if p.get("url") else p["name"]
        category = f" · {p['category']}" if p.get("category") else ""
        lines.append(f"- {title} — {p['address']}{category}")
    return lines


def fallback_report(date, recommendation, places_by_city):
    """LLM 리포트 생성이 실패했을 때 데이터만으로 만드는 리포트."""
    lines = [f"# {date} 국내 여행 추천 리포트", "",
             "> LLM 리포트 생성에 실패해 수집 데이터로만 구성한 리포트입니다.", ""]
    for i, city in enumerate(recommendation["recommended_cities"], start=1):
        name = city["city"]
        lines += [f"## {i}. {name}", "",
                  "### 추천 이유", "", city["reason"], "",
                  "### 날씨 요약", "", city["weather"], "",
                  "### 행사/축제", ""]
        lines += [f"- {e}" for e in city["events"]] or ["- 데이터 없음"]
        lines += ["", "### 맛집 추천", ""]
        lines += _places_lines(places_by_city.get(name, []))
        lines += ["", "### 1일 일정 제안", "",
                  f"- 오전: {name} 대표 명소 산책", "- 오후: 행사/축제 방문", "- 저녁: 맛집에서 식사", ""]
    return "\n".join(lines)
