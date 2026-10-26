"""HTTP 요청 — 일시 오류(5xx·연결 실패)만 1회 재시도한다.

인증(401/403)·쿼터(429)·그 밖의 4xx 는 다시 보내도 결과가 같거나 한도만 더 쓰므로 재시도하지 않는다.
응답 대기 시간 초과(ReadTimeout)도 서버가 이미 처리 중일 수 있어 재시도하지 않는다.
"""

import time

import requests

RETRY_STATUS = {500, 502, 503, 504}
RETRY_DELAY = 1.5  # 초


def send(method, url, notify=None, **kwargs):
    """requests.get/post 를 호출한다. 일시 오류면 RETRY_DELAY 뒤 1회만 다시 보낸다."""
    call = requests.get if method == "GET" else requests.post
    for attempt in (1, 2):
        try:
            response = call(url, **kwargs)
        except requests.ConnectionError as exc:   # 연결 실패·연결 타임아웃
            if attempt == 2:
                raise
            reason = type(exc).__name__
        else:
            if response.status_code not in RETRY_STATUS or attempt == 2:
                return response
            reason = f"HTTP {response.status_code}"
        if notify:
            notify(f"일시 오류({reason}) — {RETRY_DELAY:g}초 뒤 1회 재시도")
        time.sleep(RETRY_DELAY)
