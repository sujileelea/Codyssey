"""Gemini API 호출 — 1차 추천(JSON)과 최종 리포트(Markdown).

REST 엔드포인트에 `requests`로 직접 POST 한다 (SDK 미사용).
  POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
  헤더  x-goog-api-key: <키>
"""

import json
import re

import requests

import config
import net
from errors import AUTH_ERROR, LLM_ERROR, PARSE_ERROR, classify_exception, classify_http
from report import NO_PLACES

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# 1차 추천 JSON 스키마 — 필수 키(recommended_city/weather/events/reason)에
# 보너스(recommended_cities)를 더한 형태. 첫 번째 도시가 대표 추천이다.
RECOMMEND_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "recommended_cities": {
            "type": "ARRAY",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "OBJECT",
                "properties": {
                    "city": {"type": "STRING"},
                    "weather": {"type": "STRING"},
                    "events": {"type": "ARRAY", "items": {"type": "STRING"}, "minItems": 1, "maxItems": 3},
                    "reason": {"type": "STRING"},
                },
                "required": ["city", "weather", "events", "reason"],
            },
        },
    },
    "required": ["recommended_cities"],
}

CITY_KEYS = ("city", "weather", "events", "reason")


def _http_message(response):
    """오류 응답에서 사람이 읽을 메시지만 뽑는다 (Gemini 는 error.message 에 담아 준다)."""
    try:
        detail = response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        detail = response.text[:200].replace("\n", " ")
    return f"HTTP {response.status_code} {detail}"


def _classify_gemini(response):
    """Gemini 는 잘못된 키를 400(INVALID_ARGUMENT)으로 돌려주므로 인증 오류로 분류한다."""
    if response.status_code == 400 and "API key" in response.text:
        return AUTH_ERROR
    return classify_http(response.status_code)


class LLMError(Exception):
    """LLM 호출 실패 — type 은 errors 모듈의 오류 유형."""

    def __init__(self, error_type, message):
        super().__init__(message)
        self.error_type = error_type


def _generate(prompt, response_schema=None, temperature=0.7, log=None):
    """Gemini generateContent 를 호출해 텍스트를 돌려준다."""
    url = GEMINI_URL.format(model=config.GEMINI_MODEL)
    headers = {
        "x-goog-api-key": config.GEMINI_API_KEY,
        "Content-Type": "application/json",
    }
    generation_config = {"temperature": temperature}
    if response_schema is not None:
        # JSON 모드 — 응답 본문이 JSON 텍스트가 되도록 강제
        generation_config["responseMimeType"] = "application/json"
        generation_config["responseSchema"] = response_schema
    body = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
    }
    try:
        response = net.send("POST", url, notify=log, headers=headers, json=body, timeout=config.REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise LLMError(classify_exception(exc), f"{type(exc).__name__}: {exc}") from exc

    if response.status_code != 200:
        raise LLMError(_classify_gemini(response), _http_message(response))

    try:
        data = response.json()
    except ValueError as exc:
        raise LLMError(LLM_ERROR, f"응답 본문이 JSON 이 아님: {response.text[:200]}") from exc
    return _extract_text(data)


def _extract_text(data):
    """generateContent 응답에서 본문 텍스트를 꺼낸다. 차단·빈 응답은 LLMError."""
    if not isinstance(data, dict):
        raise LLMError(LLM_ERROR, "응답 형식이 객체가 아님")
    blocked = (data.get("promptFeedback") or {}).get("blockReason")
    if blocked:
        raise LLMError(LLM_ERROR, f"프롬프트가 안전 필터에 차단됨({blocked})")
    candidates = data.get("candidates") or []
    if not candidates or not isinstance(candidates[0], dict):
        raise LLMError(LLM_ERROR, "응답 후보(candidates)가 없음")
    candidate = candidates[0]
    finish = candidate.get("finishReason", "STOP")
    parts = (candidate.get("content") or {}).get("parts") or []
    # 사고(thought) 파트는 빼고 본문 텍스트만 잇는다
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought"))
    if not text.strip():
        raise LLMError(LLM_ERROR, f"응답에 텍스트가 없음(finishReason={finish})")
    # MAX_TOKENS 로 잘린 텍스트는 그대로 넘기고, 뒤의 JSON 파싱·섹션 검사가 잡는다
    return text


def parse_json_text(text):
    """LLM 텍스트에서 JSON 객체를 꺼낸다. ```json 펜스가 섞여 있어도 처리."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    return json.loads(text)


def _validate_recommendation(data, city_count):
    """필수 키와 타입을 검사하고, 대표 도시 키를 채워서 돌려준다."""
    if not isinstance(data, dict):
        raise ValueError("최상위가 JSON 객체가 아님")
    cities = data.get("recommended_cities")
    if not isinstance(cities, list) or not cities:
        raise ValueError("recommended_cities 가 비어 있거나 배열이 아님")
    cleaned = []
    for item in cities[:city_count]:
        if not isinstance(item, dict):
            raise ValueError("recommended_cities 항목이 객체가 아님")
        for key in CITY_KEYS:
            if key not in item:
                raise ValueError(f"도시 항목에 '{key}' 키가 없음")
        if not isinstance(item["city"], str) or not item["city"].strip():
            raise ValueError("city 가 빈 문자열")
        events = item["events"]
        if not isinstance(events, list) or not events:
            raise ValueError("events 가 1개 이상인 배열이 아님")
        cleaned.append({
            "city": item["city"].strip(),
            "weather": str(item["weather"]),
            "events": [str(e) for e in events][:3],
            "reason": str(item["reason"]),
        })
    first = cleaned[0]
    return {
        # 과제 필수 스키마 (대표 추천 = 첫 번째 도시)
        "recommended_city": first["city"],
        "weather": first["weather"],
        "events": first["events"],
        "reason": first["reason"],
        # 보너스: 복수 지역
        "recommended_cities": cleaned,
    }


def _recommend_prompt(date, city_count, retry=False):
    prompt = f"""당신은 국내 여행 전문가입니다. 여행 날짜 {date} 에 여행하기 좋은 대한민국 국내 지역을 {city_count}곳 추천하세요.
가장 추천하는 지역을 첫 번째에 두세요. 지역명은 '제주', '강릉', '경주'처럼 시·군 단위의 짧은 한글 이름으로 씁니다.

각 지역마다:
- city: 지역명 (짧은 한글)
- weather: 그 시기의 일반적인 날씨 요약 (1문장)
- events: 그 시기에 열리는 행사·축제 후보 1~3개 (문자열 배열, 일정은 변동 가능하다는 전제)
- reason: 추천 근거 2~4문장

반드시 아래 형태의 JSON 만 출력합니다. 설명 문장이나 코드 펜스는 붙이지 마세요.
{{"recommended_cities": [{{"city": "...", "weather": "...", "events": ["..."], "reason": "..."}}]}}"""
    if retry:
        prompt += "\n\n(이전 응답은 JSON 으로 해석되지 않았습니다. 위 필수 키만 담은 순수 JSON 을 다시 출력하세요.)"
    return prompt


def recommend(date, city_count, errors, log):
    """1차 추천 JSON 을 만든다. 파싱 실패 시 프롬프트를 고쳐 1회만 재시도한다.

    첫 시도의 파싱 실패는 재시도로 복구돼도 errors 에 남긴다.
    """
    last_error = None
    for attempt in (1, 2):
        text = _generate(_recommend_prompt(date, city_count, retry=attempt == 2), RECOMMEND_SCHEMA,
                         temperature=0.8, log=log)
        try:
            return _validate_recommendation(parse_json_text(text), city_count)
        except (ValueError, TypeError) as exc:
            last_error = f"시도 {attempt}: {exc}"
            if attempt == 1:
                errors.add("recommend", PARSE_ERROR, f"{last_error} → 필수 키만 다시 요청(재시도 1회)")
            log(f"  - JSON 파싱 실패({last_error})" + (" → 필수 키만 다시 요청" if attempt == 1 else ""))
    raise LLMError(PARSE_ERROR, f"1차 추천 JSON 파싱 2회 실패 — {last_error}")


REPORT_SECTIONS = ("추천 이유", "날씨 요약", "행사/축제", "맛집 추천", "1일 일정 제안")

def check_report(markdown, date, recommendation, places_by_city):
    """LLM 리포트가 과제 필수 항목을 다 갖췄는지 검사한다. 빠진 것이 있으면 ValueError."""
    cities = [c["city"] for c in recommendation["recommended_cities"]]
    missing = []
    if not markdown.startswith(f"# {date} 국내 여행 추천 리포트"):
        missing.append("제목")
    if not re.search(r"^##\s*추천 지역", markdown, re.MULTILINE):
        missing.append("추천 지역")
    for city in cities:
        if not re.search(rf"^##\s*(\d+\.\s*)?{re.escape(city)}", markdown, re.MULTILINE):
            missing.append(f"{city} 섹션")
    for section in REPORT_SECTIONS:
        found = len(re.findall(rf"^###\s*{re.escape(section)}", markdown, re.MULTILINE))
        if found < len(cities):
            missing.append(f"{section}({found}/{len(cities)})")
    if any(not places_by_city.get(city) for city in cities) and "데이터 없음" not in markdown:
        missing.append("맛집 0건 지역의 '데이터 없음' 표기")
    if missing:
        raise ValueError("리포트 필수 항목 누락: " + ", ".join(missing))


def write_report(date, recommendation, places_by_city, log=None):
    """최종 여행 리포트(Markdown)를 생성한다. 필수 항목이 빠지면 PARSE_ERROR 로 실패시킨다.

    실패하면 호출한 쪽이 데이터만으로 만든 대체 리포트를 쓴다.
    """
    payload = {
        "date": date,
        "recommendation": recommendation,
        "places_by_city": places_by_city,
    }
    prompt = f"""아래 JSON 데이터만 근거로 {date} 국내 여행 추천 리포트를 Markdown 으로 작성하세요.

규칙:
- 첫 줄은 정확히 `# {date} 국내 여행 추천 리포트`
- 그다음 `## 추천 지역` 섹션에 지역마다 `- 지역명 — 한 줄 요약` 을 씁니다 (첫 번째가 대표 추천)
- 이어서 `## 1. 지역명`, `## 2. 지역명` 처럼 지역별로 나누고, 각 지역 아래에 다음 소제목을 모두 둡니다:
  `### 추천 이유` (2~3문장 요약) · `### 날씨 요약` · `### 행사/축제` (목록) · `### 맛집 추천` · `### 1일 일정 제안` (오전/오후/저녁)
- 맛집은 데이터에 있는 것만 이름·주소·카테고리·링크로 목록화합니다. 데이터에 없는 맛집을 지어내지 마세요.
- 맛집 목록이 비어 있으면 `- {NO_PLACES}` 한 줄만 씁니다.
- 1일 일정 제안에는 맛집이 있으면 그중 1~2곳을 식사 시간에 넣습니다.
- 오류 요약 섹션은 프로그램이 따로 붙이므로 쓰지 않습니다. 코드 펜스 없이 Markdown 본문만 출력합니다.

데이터:
{json.dumps(payload, ensure_ascii=False, indent=2)}"""
    text = _generate(prompt, temperature=0.6, log=log).strip()
    fenced = re.fullmatch(r"```(?:markdown|md)?\s*(.*?)```", text, re.DOTALL)
    markdown = fenced.group(1).strip() if fenced else text
    # 오류 요약은 프로그램이 붙이므로, LLM 이 지시를 어기고 썼다면 잘라 낸다
    markdown = re.split(r"^##\s*오류 요약", markdown, maxsplit=1, flags=re.MULTILINE)[0].rstrip()
    try:
        check_report(markdown, date, recommendation, places_by_city)
    except ValueError as exc:
        raise LLMError(PARSE_ERROR, str(exc)) from exc
    return markdown
