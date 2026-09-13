"""Kakao Local API — 키워드로 장소 검색 (맛집).

  GET https://dapi.kakao.com/v2/local/search/keyword.json?query=<도시> 맛집&size=N
  헤더 Authorization: KakaoAK <REST API 키>

실패(인증·쿼터·네트워크·0건)해도 예외를 밖으로 내지 않고 빈 목록을 돌려주며,
오류는 `log`(ErrorLog) 에 기록한다. 리포트 생성은 계속 진행되어야 한다.
"""

import requests

import config
from errors import EMPTY_RESULT, PARSE_ERROR, classify_exception, classify_http

KAKAO_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
STEP = "place_search"


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize(document):
    """Kakao 응답 1건을 과제 최소 필드로 정리한다."""
    return {
        "name": document.get("place_name", ""),
        "address": document.get("road_address_name") or document.get("address_name", ""),
        "category": document.get("category_name", ""),
        "url": document.get("place_url", ""),
        "x": _to_float(document.get("x")),  # 경도(lng)
        "y": _to_float(document.get("y")),  # 위도(lat)
        "phone": document.get("phone", ""),
    }


def search_restaurants(city, count, errors, log=print):
    """`<city> 맛집` 키워드로 count 곳을 검색해 목록을 돌려준다 (실패·0건이면 [])."""
    query = f"{city} 맛집"
    params = {"query": query, "size": max(1, min(count, 15)), "category_group_code": "FD6"}
    headers = {"Authorization": f"KakaoAK {config.KAKAO_REST_API_KEY}"}

    try:
        response = requests.get(KAKAO_URL, headers=headers, params=params, timeout=config.REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        error_type = classify_exception(exc)
        errors.add(STEP, error_type, f"{type(exc).__name__}: {exc} (query={query})")
        log(f"  - 오류: 네트워크 실패({type(exc).__name__}). 맛집 섹션은 '데이터 없음'으로 처리하고 계속 진행합니다.")
        return []

    if response.status_code != 200:
        error_type = classify_http(response.status_code)
        errors.add(STEP, error_type, f"HTTP {response.status_code} (query={query})")
        hint = {
            401: "인증 실패(401). 키 설정을 확인하세요.",
            403: "권한 없음(403). 카카오맵 활성화 설정·앱 권한을 확인하세요.",
            429: "호출 한도 초과(429).",
        }.get(response.status_code, f"HTTP {response.status_code}.")
        log(f"  - 오류: {hint}")
        log("  - 맛집 섹션은 '데이터 없음'으로 처리하고 계속 진행합니다.")
        return []

    try:
        documents = response.json()["documents"]
    except (ValueError, KeyError, TypeError) as exc:
        errors.add(STEP, PARSE_ERROR, f"{type(exc).__name__}: {exc} (query={query})")
        log("  - 오류: 응답 JSON 해석 실패. 맛집 섹션은 '데이터 없음'으로 처리합니다.")
        return []

    places = [_normalize(d) for d in documents][:count]
    if not places:
        errors.add(STEP, EMPTY_RESULT, f"0 results for query={query}")
        log("  - 검색 결과 0건(키워드를 바꿔 재시도하지 않고 다음 단계로 진행)")
    return places
