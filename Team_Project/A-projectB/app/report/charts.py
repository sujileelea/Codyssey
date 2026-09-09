"""matplotlib 차트 → PNG (한글 폰트 자동 적용).

- 카테고리별 뉴스 수 (막대)
- 일자별 수집 추이 (선, collected_at 기준)
- 감성 분포 (막대, 보너스)
"""

from __future__ import annotations

import logging
import platform
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 서버·CLI 환경: 화면 없이 파일로만 저장
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

logger = logging.getLogger(__name__)

FONT_CANDIDATES = {
    "Darwin": ["AppleGothic", "Apple SD Gothic Neo", "NanumGothic"],
    "Windows": ["Malgun Gothic", "NanumGothic", "Gulim"],
    "Linux": ["NanumGothic", "NanumBarunGothic", "Noto Sans CJK KR", "Noto Sans KR"],
}
PALETTE = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3", "#937860"]
SENTIMENT_LABELS = {"positive": "긍정", "neutral": "중립", "negative": "부정"}
SENTIMENT_COLORS = {"positive": "#55A868", "neutral": "#8C8C8C", "negative": "#C44E52"}


def setup_korean_font(font_family: str | None = None) -> str:
    """OS별 한글 폰트를 찾아 matplotlib에 적용하고 적용된 폰트명을 반환한다."""
    installed = {f.name for f in font_manager.fontManager.ttflist}
    candidates = ([font_family] if font_family else []) + FONT_CANDIDATES.get(platform.system(), [])
    for name in candidates:
        if name in installed:
            plt.rcParams["font.family"] = name
            plt.rcParams["axes.unicode_minus"] = False
            return name
    logger.warning("한글 폰트를 찾지 못해 기본 폰트를 사용합니다 (한글이 깨질 수 있음)")
    return plt.rcParams["font.family"][0] if plt.rcParams["font.family"] else "default"


def _save(fig: plt.Figure, out_path: Path) -> str:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    logger.info("차트 저장: %s", out_path)
    return str(out_path)


def chart_by_category(rows: list[tuple[str, int]], out_path: Path, title: str = "카테고리별 뉴스 수") -> str:
    labels = [r[0] for r in rows] or ["(없음)"]
    values = [r[1] for r in rows] or [0]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    bars = ax.bar(labels, values, color=PALETTE[: len(labels)])
    ax.bar_label(bars, padding=2)
    ax.set_title(title)
    ax.set_ylabel("건수")
    ax.spines[["top", "right"]].set_visible(False)
    return _save(fig, out_path)


def chart_by_date(rows: list[tuple[str, int]], out_path: Path, title: str = "일자별 수집 추이") -> str:
    labels = [r[0] for r in rows] or ["(없음)"]
    values = [r[1] for r in rows] or [0]
    fig, ax = plt.subplots(figsize=(7, 4.2))
    ax.plot(labels, values, marker="o", color=PALETTE[0], linewidth=2)
    for x, y in zip(labels, values):
        ax.annotate(str(y), (x, y), textcoords="offset points", xytext=(0, 6), ha="center", fontsize=9)
    ax.set_title(title)
    ax.set_ylabel("수집 건수")
    ax.set_xlabel("수집 일자")
    ax.set_ylim(bottom=0)
    ax.spines[["top", "right"]].set_visible(False)
    fig.autofmt_xdate()
    return _save(fig, out_path)


def chart_by_sentiment(rows: list[tuple[str, int]], out_path: Path, title: str = "뉴스 감성 분포") -> str:
    order = ["positive", "neutral", "negative"]
    counts = {label: 0 for label in order}
    for label, count in rows:
        counts[label] = counts.get(label, 0) + count
    labels = [SENTIMENT_LABELS[k] for k in order]
    values = [counts[k] for k in order]
    fig, ax = plt.subplots(figsize=(6, 4.2))
    bars = ax.bar(labels, values, color=[SENTIMENT_COLORS[k] for k in order])
    ax.bar_label(bars, padding=2)
    ax.set_title(title)
    ax.set_ylabel("건수")
    ax.spines[["top", "right"]].set_visible(False)
    return _save(fig, out_path)
