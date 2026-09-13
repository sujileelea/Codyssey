"""실행 중 발생한 오류를 모아 두는 목록.

프로그램은 오류가 나도 가능한 한 계속 진행하고, 결과 JSON과 리포트의
`errors` 섹션에 요약을 남긴다.
"""

import requests

# 오류 유형 — 과제에서 요구한 대표 오류(인증/쿼터/네트워크/파싱)와 그 외
AUTH_ERROR = "AUTH_ERROR"        # 401/403 — 키·권한 문제
QUOTA_ERROR = "QUOTA_ERROR"      # 429 — 호출 한도 초과
NETWORK_ERROR = "NETWORK_ERROR"  # 연결 실패·타임아웃
HTTP_ERROR = "HTTP_ERROR"        # 그 밖의 4xx/5xx
PARSE_ERROR = "PARSE_ERROR"      # 응답이 기대한 JSON/구조가 아님
EMPTY_RESULT = "EMPTY_RESULT"    # 검색 결과 0건
LLM_ERROR = "LLM_ERROR"          # LLM 응답 없음·차단 등


class ErrorLog:
    """`{"step", "type", "message"}` 딕셔너리의 리스트."""

    def __init__(self):
        self.items = []

    def add(self, step, error_type, message):
        entry = {"step": step, "type": error_type, "message": str(message)}
        self.items.append(entry)
        return entry

    def __len__(self):
        return len(self.items)

    def __iter__(self):
        return iter(self.items)


def classify_http(status_code):
    """HTTP 상태 코드를 오류 유형으로 바꾼다."""
    if status_code in (401, 403):
        return AUTH_ERROR
    if status_code == 429:
        return QUOTA_ERROR
    return HTTP_ERROR


def classify_exception(exc):
    """requests 예외를 오류 유형으로 바꾼다."""
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return NETWORK_ERROR
    return HTTP_ERROR
