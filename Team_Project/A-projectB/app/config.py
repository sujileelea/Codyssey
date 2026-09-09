"""설정 로더.

- `config.json`: 뉴스 소스 URL, 중복 정책, AI 모델, 경로 등 (비밀 없음)
- `.env`: API 키 값 (`GEMINI_API_KEY`). config.json에는 환경변수 **이름**만 둔다.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).resolve().parent

REQUIRED_SECTIONS = ("database", "cleaning", "sources", "http", "ai", "summary", "analysis", "sentiment", "report", "logging")


def _load_dotenv(path: Path) -> None:
    """python-dotenv가 없어도 동작하도록 `.env`를 직접 읽는다 (KEY=VALUE, # 주석)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class AppConfig:
    raw: dict[str, Any]
    base_dir: Path

    def section(self, name: str) -> dict[str, Any]:
        return self.raw[name]

    @property
    def database(self) -> dict[str, Any]:
        return self.raw["database"]

    @property
    def cleaning(self) -> dict[str, Any]:
        return self.raw["cleaning"]

    @property
    def sources(self) -> dict[str, Any]:
        return self.raw["sources"]

    @property
    def http(self) -> dict[str, Any]:
        return self.raw["http"]

    @property
    def ai(self) -> dict[str, Any]:
        return self.raw["ai"]

    @property
    def summary(self) -> dict[str, Any]:
        return self.raw["summary"]

    @property
    def analysis(self) -> dict[str, Any]:
        return self.raw["analysis"]

    @property
    def sentiment(self) -> dict[str, Any]:
        return self.raw["sentiment"]

    @property
    def report(self) -> dict[str, Any]:
        return self.raw["report"]

    @property
    def logging(self) -> dict[str, Any]:
        return self.raw["logging"]

    def resolve(self, relative: str) -> Path:
        """config 안의 상대 경로를 app 디렉터리 기준 절대 경로로 바꾼다."""
        path = Path(relative)
        return path if path.is_absolute() else self.base_dir / path

    @property
    def db_path(self) -> Path:
        return self.resolve(self.database["path"])

    @property
    def categories(self) -> list[str]:
        return list(self.cleaning.get("categories", []))


def load_config(path: str | Path = "config.json") -> AppConfig:
    """config.json과 .env를 읽는다. 상대 경로는 cwd → app 디렉터리 순으로 찾는다."""
    candidates = [Path(path)]
    if not Path(path).is_absolute():
        candidates.append(BASE_DIR / path)
    config_path = next((p for p in candidates if p.exists()), None)
    if config_path is None:
        raise FileNotFoundError(f"설정 파일을 찾을 수 없습니다: {path}")

    with config_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    missing = [key for key in REQUIRED_SECTIONS if key not in raw]
    if missing:
        raise ValueError(f"config.json에 필요한 섹션이 없습니다: {', '.join(missing)}")

    base_dir = config_path.resolve().parent
    _load_dotenv(base_dir / ".env")
    return AppConfig(raw=raw, base_dir=base_dir)
