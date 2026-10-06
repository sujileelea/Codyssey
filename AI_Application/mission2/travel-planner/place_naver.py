"""장소 검색 제공자 — Naver 지역 검색 (PLACE_PROVIDER=naver 일 때).

  GET https://openapi.naver.com/v1/search/local.json?query=<키워드>&display=N&sort=comment
  헤더 X-Naver-Client-Id / X-Naver-Client-Secret

Kakao 와 같은 함수 이름·반환 모양을 지켜, 파이프라인 코드는 바꾸지 않고 설정만으로 교체한다.
"""

import re
from urllib.parse import quote

import config

NAME = "naver_local_search"
LABEL = "Naver Local"
URL = "https://openapi.naver.com/v1/search/local.json"
MAX_SIZE = 5                       # display 상한
KEY_NAMES = ("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET")
STATUS_HINTS = {
    401: "인증 실패(401). Client ID/Secret 값과 헤더 이름(X-Naver-Client-Id/Secret)을 확인하세요.",
    403: "권한 없음(403). 애플리케이션의 '검색' API 사용 설정을 확인하세요.",
}


def build_request(query, size):
    """(headers, params) — sort=comment: 리뷰 많은 순."""
    headers = {"X-Naver-Client-Id": config.NAVER_CLIENT_ID, "X-Naver-Client-Secret": config.NAVER_CLIENT_SECRET}
    params = {"query": query, "display": size, "sort": "comment"}
    return headers, params


def documents(data):
    return data["items"]


def _coord(value):
    """mapx/mapy 는 WGS84 좌표 × 10^7 정수 문자열. 예전 형식(KATEC)처럼 작으면 변환하지 않고 None."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number / 1e7 if number > 1e8 else None


def normalize(item):
    """응답 1건 → 공통 필드 (title 의 <b> 강조 태그 제거)."""
    return {
        "name": re.sub(r"<[^>]+>", "", item.get("title", "")),
        "address": item.get("roadAddress") or item.get("address", ""),
        "category": item.get("category", "").replace(">", " > "),
        "url": item.get("link", ""),
        "x": _coord(item.get("mapx")),
        "y": _coord(item.get("mapy")),
        "phone": item.get("telephone", ""),
    }


def search_url(query):
    return f"https://map.naver.com/p/search/{quote(query)}"
