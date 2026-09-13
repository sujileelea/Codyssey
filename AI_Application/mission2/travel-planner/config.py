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

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "60"))

KEY_GUIDE = f"""
API 키가 설정되지 않았습니다: {{missing}}

설정 방법 (둘 중 하나):
  1) .env 파일 — {ENV_FILE}
       cp .env.example .env   후 값 채우기
       GEMINI_API_KEY=...        # https://aistudio.google.com/ → Get API key
       KAKAO_REST_API_KEY=...    # https://developers.kakao.com/ → 내 애플리케이션 → 앱 키 → REST API 키
                                 #   (앱 설정 → 카카오맵 → 활성화 설정 ON 필요)
  2) 환경변수 (현재 터미널 세션에만 적용)
       macOS/Linux:  export GEMINI_API_KEY="YOUR_KEY"
       PowerShell:   $env:GEMINI_API_KEY="YOUR_KEY"

키 값은 코드·README·결과 파일에 절대 쓰지 않는다. (.env는 .gitignore로 제외)
"""


def require_keys():
    """필수 키가 하나라도 없으면 설정 방법을 안내하고 즉시 종료한다."""
    missing = []
    if not GEMINI_API_KEY:
        missing.append("GEMINI_API_KEY")
    if not KAKAO_REST_API_KEY:
        missing.append("KAKAO_REST_API_KEY")
    if missing:
        print(KEY_GUIDE.format(missing=", ".join(missing)), file=sys.stderr)
        sys.exit(1)
