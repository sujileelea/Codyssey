"""장소 검색 공통 창구 — 파이프라인은 이 모듈만 부른다.

제공자(Kakao·Naver)는 place_kakao.py · place_naver.py 에 같은 모양으로 두고, 설정 PLACE_PROVIDER 로 고른다.
제공자를 바꾸거나 새로 붙여도 파이프라인·리포트 코드는 그대로다 — 결과는 항상 공통 필드
{name, address, category, url, x, y, phone} 의 목록이다.

실패(인증·쿼터·네트워크·0건)해도 예외를 밖으로 내지 않고 빈 목록을 돌려주며,
오류는 errors(ErrorLog) 에 기록한다. 리포트 생성은 계속 진행되어야 한다.
"""

import re

import requests

import config
import net
import place_kakao
import place_naver
from errors import EMPTY_RESULT, PARSE_ERROR, classify_exception, classify_http

PROVIDERS = {"kakao": place_kakao, "naver": place_naver}
STEP = "place_search"
SKIP_NOTE = "맛집 섹션은 '데이터 없음'으로 처리하고 계속 진행합니다."

# --- 검색어 정규화 -------------------------------------------------------------
# LLM 이 '강원도'·'부산광역시'·'경북 경주시'처럼 넓거나 긴 이름을 주면 검색 품질이 떨어진다.
ADMIN_SUFFIXES = ("특별자치도", "특별자치시", "특별시", "광역시")
# 도 단위로 나오면 여행 대표 도시로 보정한다 — 기준을 바꾸려면 이 표만 고친다
PROVINCE_TO_CITY = {
    "강원": "강릉", "경기": "수원", "충북": "단양", "충남": "공주", "전북": "전주",
    "전남": "여수", "경북": "경주", "경남": "통영",
}
PROVINCE_ALIASES = {
    "강원도": "강원", "강원특별자치도": "강원", "경기도": "경기", "충청북도": "충북", "충청남도": "충남",
    "전라북도": "전북", "전북특별자치도": "전북", "전라남도": "전남", "경상북도": "경북", "경상남도": "경남",
}


def provider():
    return PROVIDERS[config.PLACE_PROVIDER]


def label():
    return provider().LABEL


def max_size():
    return provider().MAX_SIZE


def normalize_city(city):
    """지역명 → 장소 검색용 짧은 키워드.

    '제주(서귀포)' → 제주 · '여수/순천' → 여수 · '경북 경주시' → 경주 · '부산광역시' → 부산 · '강원도' → 강릉
    """
    name = re.sub(r"\(.*?\)", " ", city)              # 괄호 설명 제거
    name = re.split(r"[,/·]", name)[0].strip() or city.strip()
    tokens = name.split()
    if len(tokens) > 1:                               # 여러 단어면 가장 구체적인 마지막 단어
        name = tokens[-1]
    province = PROVINCE_ALIASES.get(name, name)
    if province in PROVINCE_TO_CITY:                  # 도 단위 → 대표 도시
        return PROVINCE_TO_CITY[province]
    for suffix in ADMIN_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[:-len(suffix)]
    if name.endswith(("시", "군")) and len(name) >= 3:  # 강릉시 → 강릉, 양양군 → 양양
        return name[:-1]
    return name


def query_for(city):
    return f"{normalize_city(city)} 맛집"


def search_url(city):
    """0건일 때 리포트에 넣는 '지도에서 직접 찾기' 링크."""
    return provider().search_url(query_for(city))


def search_restaurants(city, count, errors, log=print):
    """`<정규화한 지역명> 맛집` 으로 count 곳을 검색해 공통 필드 목록을 돌려준다 (실패·0건이면 [])."""
    source = provider()
    query = query_for(city)
    if query != f"{city} 맛집":
        log(f"검색어 보정: '{city}' → '{query}'")
    headers, params = source.build_request(query, max(1, min(count, source.MAX_SIZE)))

    try:
        response = net.send("GET", source.URL, notify=log, headers=headers, params=params,
                            timeout=config.REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        errors.add(STEP, classify_exception(exc), f"{type(exc).__name__}: {exc} (query={query})")
        log(f"오류: 네트워크 실패({type(exc).__name__}). 인터넷 연결을 확인하세요.")
        log(SKIP_NOTE)
        return []

    if response.status_code != 200:
        errors.add(STEP, classify_http(response.status_code), f"HTTP {response.status_code} (query={query})")
        hint = source.STATUS_HINTS.get(response.status_code) or {
            429: "호출 한도 초과(429).",
        }.get(response.status_code, f"HTTP {response.status_code}.")
        log(f"오류: {hint}")
        log(SKIP_NOTE)
        return []

    try:
        places = [source.normalize(d) for d in source.documents(response.json())][:count]
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        errors.add(STEP, PARSE_ERROR, f"{type(exc).__name__}: {exc} (query={query})")
        log("오류: 응답 JSON 해석 실패.")
        log(SKIP_NOTE)
        return []

    if not places:
        errors.add(STEP, EMPTY_RESULT, f"0 results for query={query}")
        log("검색 결과 0건(키워드를 바꿔 재시도하지 않고 다음 단계로 진행)")
    return places
