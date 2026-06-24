#!/bin/bash
# 공고 분석 챗봇 실행 런처 (macOS: 더블클릭하면 실행)
cd "$(dirname "$0")" || exit 1

echo "▶ 공고 분석 챗봇을 시작합니다..."

# 1) 가상환경 준비 (최초 1회만 생성)
if [ ! -d ".venv" ]; then
  echo "  · 가상환경 생성 중..."
  python3 -m venv .venv || { echo "python3 가 필요합니다."; exit 1; }
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# 2) 의존성 설치
echo "  · 의존성 확인/설치 중..."
pip install -q -r requirements.txt

# 3) 포트 선택 (8000 사용 중이면 8137)
PORT=8000
if lsof -i :$PORT >/dev/null 2>&1; then PORT=8137; fi

# 4) 브라우저 자동 열기 + 서버 실행
echo "  · http://localhost:$PORT 에서 실행합니다. (종료: 이 창에서 Ctrl+C)"
( sleep 2; open "http://localhost:$PORT" ) &
exec python3 -m uvicorn main:app --port "$PORT"
