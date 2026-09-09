"""HTTP 요청 공통: 타임아웃·재시도·요청 간 지연·오류 처리."""

from __future__ import annotations

import logging
import time

import requests

logger = logging.getLogger(__name__)


class FetchError(Exception):
    """재시도 후에도 실패한 HTTP 요청."""


class HttpClient:
    def __init__(self, http_config: dict):
        self.timeout = float(http_config.get("timeout", 10))
        self.retries = int(http_config.get("retries", 2))
        self.delay = float(http_config.get("delay_seconds", 1.5))
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": http_config.get("user_agent", "A-projectB-news-cli/0.1"),
                "Accept-Language": "ko,en;q=0.8",
            }
        )
        self._last_request_at = 0.0

    def _wait_for_delay(self) -> None:
        """요청 간 최소 지연을 보장한다 (크롤링 정책 준수)."""
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    def get(self, url: str) -> requests.Response:
        """GET 요청. 타임아웃·연결 오류·5xx는 재시도, 4xx는 즉시 실패."""
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 2):
            self._wait_for_delay()
            self._last_request_at = time.monotonic()
            try:
                response = self.session.get(url, timeout=self.timeout)
                if response.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {response.status_code}", response=response)
                response.raise_for_status()
                return response
            except requests.Timeout as error:
                last_error = error
                logger.warning("타임아웃 (%s/%s): %s", attempt, self.retries + 1, url)
            except requests.ConnectionError as error:
                last_error = error
                logger.warning("연결 실패 (%s/%s): %s", attempt, self.retries + 1, url)
            except requests.HTTPError as error:
                status = error.response.status_code if error.response is not None else "?"
                if isinstance(status, int) and 400 <= status < 500:
                    raise FetchError(f"HTTP {status}: {url}") from error
                last_error = error
                logger.warning("서버 오류 %s (%s/%s): %s", status, attempt, self.retries + 1, url)
            if attempt <= self.retries:
                time.sleep(self.delay * attempt)  # 지수 백오프 대신 선형 증가 (소량 요청)
        raise FetchError(f"요청 실패: {url} ({last_error})") from last_error
