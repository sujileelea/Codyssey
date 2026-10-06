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
IO_ERROR = "IO_ERROR"            # 결과 파일 저장 실패

# 오류 유형별 다음 행동 안내 — CLI 요약과 웹 화면이 같이 쓴다
HINTS = {
    AUTH_ERROR: "키 값·권한을 확인하세요 (Kakao: REST API 키·카카오맵 활성화 / Naver: Client ID·Secret·검색 API "
                "사용 설정 / Gemini: AI Studio 키)",
    QUOTA_ERROR: "호출 한도를 넘었습니다 — 잠시 뒤 다시 실행하세요",
    NETWORK_ERROR: "인터넷 연결을 확인한 뒤 다시 실행하세요",
    HTTP_ERROR: "서비스 쪽 일시 오류일 수 있습니다 — 잠시 뒤 다시 실행하세요",
    PARSE_ERROR: "LLM 응답 형식 문제입니다 — 다시 실행하면 대개 해결됩니다",
    EMPTY_RESULT: "검색 결과가 없습니다 — 다른 날짜로 다시 추천받아 보세요",
    LLM_ERROR: "LLM 이 본문을 돌려주지 않았습니다(안전 필터 등) — 다시 실행하세요",
    IO_ERROR: "results 폴더의 쓰기 권한·디스크 공간을 확인하세요",
}


def hint(error_type):
    return HINTS.get(error_type, "")


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
