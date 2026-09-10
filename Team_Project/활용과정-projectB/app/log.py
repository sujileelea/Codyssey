"""logging 설정. 전체 CLI에서 한 번만 호출한다.

- 콘솔: `[LEVEL] message` (과제 결과 예시 형식)
- 파일: `logs/app.log`에 시각·모듈 포함
"""

from __future__ import annotations

import logging
from pathlib import Path

CONSOLE_FORMAT = "[%(levelname)s] %(message)s"
FILE_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def setup_logging(level: str = "INFO", log_file: Path | None = None, verbose: bool = False) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG if verbose else getattr(logging, level.upper(), logging.INFO))

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(CONSOLE_FORMAT))
    root.addHandler(console)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(FILE_FORMAT))
        root.addHandler(file_handler)

    # 외부 라이브러리의 과도한 로그를 줄인다.
    for noisy in ("urllib3", "httpx", "httpcore", "google", "google_genai", "matplotlib", "PIL"):
        logging.getLogger(noisy).setLevel(logging.ERROR)
