"""Gemini API 호출 — 1차 추천(JSON)과 최종 리포트(Markdown).

REST 엔드포인트에 `requests`로 직접 POST 한다 (SDK 미사용).
  POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent
  헤더  x-goog-api-key: <키>
"""

import json
import re

import requests

import config
from errors import AUTH_ERROR, LLM_ERROR, PARSE_ERROR, classify_exception, classify_http

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# 1차 추천 JSON 스키마 — 필수 키(recommended_city/weather/events/reason)에
# 보너스(recommended_cities)를 더한 형태. 첫 번째 도시가 대표 추천이다.
RECOMMEND_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "recommended_cities": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "city": {"type": "STRING"},
                    "weather": {"type": "STRING"},
                    "events": {"type": "ARRAY", "items": {"type": "STRING"}},
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


def _generate(prompt, response_schema=None, temperature=0.7):
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
        response = requests.post(url, headers=headers, json=body, timeout=config.REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise LLMError(classify_exception(exc), f"{type(exc).__name__}: {exc}") from exc

    if response.status_code != 200:
        raise LLMError(_classify_gemini(response), _http_message(response))

    try:
        data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        # 안전 필터 차단 등으로 candidates 가 비어 있을 수 있다
        raise LLMError(LLM_ERROR, f"응답에 텍스트가 없음: {response.text[:200]}") from exc


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
        if not isinstance(events, list):
            raise ValueError("events 가 배열이 아님")
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


def recommend(date, city_count, log):
    """1차 추천 JSON 을 만든다. 파싱 실패 시 프롬프트를 고쳐 1회만 재시도한다."""
    last_error = None
    for attempt in (1, 2):
        text = _generate(_recommend_prompt(date, city_count, retry=attempt == 2), RECOMMEND_SCHEMA, temperature=0.8)
        try:
            return _validate_recommendation(parse_json_text(text), city_count)
        except (ValueError, TypeError) as exc:
            last_error = f"시도 {attempt}: {exc}"
            log(f"  - JSON 파싱 실패({last_error})" + (" → 필수 키만 다시 요청" if attempt == 1 else ""))
    raise LLMError(PARSE_ERROR, f"1차 추천 JSON 파싱 2회 실패 — {last_error}")


def write_report(date, recommendation, places_by_city):
    """최종 여행 리포트(Markdown)를 생성한다. 맛집 0건인 도시는 '데이터 없음'으로 표기하게 한다."""
    payload = {
        "date": date,
        "recommendation": recommendation,
        "places_by_city": places_by_city,
    }
    prompt = f"""아래 JSON 데이터만 근거로 {date} 국내 여행 추천 리포트를 Markdown 으로 작성하세요.

규칙:
- 첫 줄은 정확히 `# {date} 국내 여행 추천 리포트`
- 지역이 여러 개면 `## 1. 지역명`, `## 2. 지역명` 처럼 지역별로 나누고, 각 지역 아래에 다음 소제목을 모두 둡니다:
  `### 추천 이유` (2~3문장 요약) · `### 날씨 요약` · `### 행사/축제` (목록) · `### 맛집 추천` · `### 1일 일정 제안` (오전/오후/저녁)
- 맛집은 데이터에 있는 것만 이름·주소·카테고리·링크로 목록화합니다. 데이터에 없는 맛집을 지어내지 마세요.
- 맛집 목록이 비어 있으면 `- 데이터 없음 (장소 검색 결과 0건)` 한 줄만 씁니다.
- 1일 일정 제안에는 맛집이 있으면 그중 1~2곳을 식사 시간에 넣습니다.
- 오류 요약 섹션은 프로그램이 따로 붙이므로 쓰지 않습니다. 코드 펜스 없이 Markdown 본문만 출력합니다.

데이터:
{json.dumps(payload, ensure_ascii=False, indent=2)}"""
    text = _generate(prompt, temperature=0.6).strip()
    fenced = re.fullmatch(r"```(?:markdown|md)?\s*(.*?)```", text, re.DOTALL)
    return fenced.group(1).strip() if fenced else text
