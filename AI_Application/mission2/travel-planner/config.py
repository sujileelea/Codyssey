"""환경변수(.env) 로드와 API 키 확인.

키는 코드에 쓰지 않고 이 파일과 같은 폴더의 `.env` 또는 셸 환경변수에서 읽는다.
"""

import os
import sys

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, ".env")
RESULTS_DIR = os.path.join(BASE_DIR, "results")

# 이미 셸에 설정된 값이 .env보다 우선한다 (override=False)
load_dotenv(ENV_FILE, override=False)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "").strip()

# 장소 검색 제공자 — kakao(기본) | naver. 바꾸면 그 제공자의 키가 필요하다
PLACE_PROVIDER = os.getenv("PLACE_PROVIDER", "kakao").strip().lower()
NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID", "").strip()
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET", "").strip()
PROVIDER_KEYS = {"kakao": ("KAKAO_REST_API_KEY",), "naver": ("NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET")}
# 선택 — 웹 화면의 카카오 지도용 JavaScript 키(브라우저에 공개되는 키). 없으면 OpenStreetMap 으로 표시
KAKAO_JS_KEY = os.getenv("KAKAO_JS_KEY", "").strip()

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "60"))

KEY_GUIDE = f"""
API 키가 설정되지 않았습니다: {{missing}}{{state}}

설정 방법 (둘 중 하나):
  1) .env 파일 — {ENV_FILE}
       cp -n .env.example .env   (-n: 이미 있는 .env 를 덮어쓰지 않음) 후 값 채우기
       GEMINI_API_KEY=...        # https://aistudio.google.com/ → Get API key
       KAKAO_REST_API_KEY=...    # https://developers.kakao.com/ → 내 애플리케이션 → 앱 키 → REST API 키
                                 #   (앱 설정 → 카카오맵 → 활성화 설정 ON 필요)
       # 네이버로 검색하려면 PLACE_PROVIDER=naver + NAVER_CLIENT_ID / NAVER_CLIENT_SECRET
       #   (https://developers.naver.com/ → 애플리케이션 등록 → 사용 API: 검색)
  2) 환경변수 (현재 터미널 세션에만 적용)
       macOS/Linux:  export GEMINI_API_KEY="YOUR_KEY"
       PowerShell:   $env:GEMINI_API_KEY="YOUR_KEY"

키 값은 코드·README·결과 파일에 절대 쓰지 않는다. (.env는 .gitignore로 제외)
"""


def missing_keys():
    """비어 있는 필수 키 이름 목록 — Gemini + 고른 장소 검색 제공자의 키."""
    names = ("GEMINI_API_KEY",) + PROVIDER_KEYS.get(PLACE_PROVIDER, ())
    return [name for name in names if not globals()[name]]


def require_keys():
    """설정이 잘못됐거나 필수 키가 하나라도 없으면 설정 방법을 안내하고 즉시 종료한다."""
    if PLACE_PROVIDER not in PROVIDER_KEYS:
        print(f"PLACE_PROVIDER 값이 올바르지 않습니다: '{PLACE_PROVIDER}' (가능: {', '.join(PROVIDER_KEYS)})",
              file=sys.stderr)
        sys.exit(1)
    missing = missing_keys()
    if missing:
        # .env 는 있는데 값이 비어 있는 경우(템플릿을 그대로 복사했거나 덮어쓴 경우)를 따로 알린다
        state = "\n  → .env 파일은 있지만 위 키의 값이 비어 있습니다" if os.path.exists(ENV_FILE) else "\n  → .env 파일이 없습니다"
        print(KEY_GUIDE.format(missing=", ".join(missing), state=state), file=sys.stderr)
        sys.exit(1)
