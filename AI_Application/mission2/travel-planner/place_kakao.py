"""장소 검색 제공자 — Kakao Local 키워드 검색.

  GET https://dapi.kakao.com/v2/local/search/keyword.json?query=<키워드>&size=N&category_group_code=FD6
  헤더 Authorization: KakaoAK <REST API 키>

제공자 모듈은 요청 모양·응답 꺼내기·필드 정리만 안다. 호출·오류 처리는 place_api 가 공통으로 한다.
"""

from urllib.parse import quote

import config

NAME = "kakao_local_keyword"
LABEL = "Kakao Local"
URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
MAX_SIZE = 15                      # size 상한
STATUS_HINTS = {
    401: "인증 실패(401). 키 설정을 확인하세요.",
    403: "권한 없음(403). 카카오맵 활성화 설정·앱 권한을 확인하세요.",
}


def build_request(query, size):
    """(headers, params) — FD6 = 음식점 카테고리로 좁힌다."""
    headers = {"Authorization": f"KakaoAK {config.KAKAO_REST_API_KEY}"}
    params = {"query": query, "size": size, "category_group_code": "FD6"}
    return headers, params


def documents(data):
    return data["documents"]


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize(document):
    """응답 1건 → 공통 필드."""
    return {
        "name": document.get("place_name", ""),
        "address": document.get("road_address_name") or document.get("address_name", ""),
        "category": document.get("category_name", ""),
        "url": document.get("place_url", ""),
        "x": _to_float(document.get("x")),  # 경도(lng)
        "y": _to_float(document.get("y")),  # 위도(lat)
        "phone": document.get("phone", ""),
    }


def search_url(query):
    """검색 결과가 없을 때 사용자가 직접 찾아볼 수 있는 지도 링크."""
    return f"https://map.kakao.com/?q={quote(query)}"
