#!/usr/bin/env bash
#
# Lateral-To-Pattern 실행 스크립트
# ---------------------------------
# 처음 받은 사람도 `./run.sh` 한 번이면 환경 구성부터 실행까지 끝납니다.
# uv가 가상환경(.venv)과 의존성 설치를 알아서 처리합니다.
#
# 사용법:
#   ./run.sh                 # 기본 실행 (콘솔에서 모델 폴더 선택)
#   ./run.sh --verbose       # main.py 인자는 그대로 전달됩니다
#   ./run.sh --run-label test
#
set -euo pipefail

cd "$(dirname "$0")"

# ── 1. uv 준비 ────────────────────────────────────────────────────────────────
if ! command -v uv >/dev/null 2>&1; then
    # Homebrew 등으로 설치했지만 PATH에 없는 경우를 먼저 확인
    for candidate in "$HOME/.local/bin/uv" "/opt/homebrew/bin/uv" "/usr/local/bin/uv"; do
        if [ -x "$candidate" ]; then
            export PATH="$(dirname "$candidate"):$PATH"
            break
        fi
    done
fi

if ! command -v uv >/dev/null 2>&1; then
    echo "[run.sh] 이 프로젝트는 uv가 필요합니다. (https://docs.astral.sh/uv/)"
    if [ -t 0 ]; then
        printf "[run.sh] 지금 설치할까요? (astral.sh 공식 스크립트 실행) [Y/n] "
        read -r answer
        case "${answer:-y}" in
            [Nn]*)
                echo "[run.sh] 설치를 건너뜁니다. 직접 설치 후 다시 실행하세요:"
                echo "         curl -LsSf https://astral.sh/uv/install.sh | sh"
                echo "         (macOS Homebrew: brew install uv)"
                exit 1
                ;;
        esac
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="$HOME/.local/bin:$PATH"
    else
        echo "[run.sh] 아래 명령으로 설치한 뒤 다시 실행하세요:"
        echo "         curl -LsSf https://astral.sh/uv/install.sh | sh"
        echo "         (macOS Homebrew: brew install uv)"
        exit 1
    fi
fi

# ── 2. API 키 확인 (없으면 미리 안내) ─────────────────────────────────────────
if [ ! -s "config/APIkey" ] \
   && [ -z "${GEMINI_API_KEY:-}" ] \
   && [ -z "${GEMINI_API_KEY_FILE:-}" ] \
   && [ ! -s ".env" ] \
   && [ ! -s "$HOME/Documents/geminiapi.txt" ]; then
    echo "[run.sh] Gemini API 키를 찾을 수 없습니다. 아래 중 하나를 설정하세요:"
    echo "         1) echo \"your_api_key\" > config/APIkey"
    echo "         2) export GEMINI_API_KEY_FILE=/path/to/keyfile"
    echo "         3) export GEMINI_API_KEY=your_api_key"
    exit 1
fi

# ── 3. 입력 이미지 확인 ───────────────────────────────────────────────────────
# images/ 는 .gitignore 대상이라 clone 직후에는 비어 있습니다.
# images/ 바로 아래에 신발 사진들과 가이드라인 이미지를 두면 됩니다.
img_files="$(find images -maxdepth 1 -type f \
    \( -iname '*.png' -o -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.webp' \) 2>/dev/null || true)"

if [ -z "$img_files" ]; then
    echo "[run.sh] images/ 바로 아래에 이미지가 없습니다. 다음처럼 넣어주세요:"
    echo "         images/가이드라인.jpg     ← 펼칠 틀 (파일명에 '가이드라인' 포함)"
    echo "         images/나이키 탄준.jpg    ← 신발 실물 사이드뷰 (여러 장 가능)"
    exit 1
fi

if ! printf '%s\n' "$img_files" | grep -qiE '가이드라인|가이드|guideline|guide'; then
    echo "[run.sh] images/ 에서 가이드라인 이미지를 찾지 못했습니다."
    echo "         파일명에 '가이드라인'(또는 guideline)이 들어간 이미지를 넣어주세요."
    exit 1
fi

# ── 4. 의존성 동기화 후 실행 ──────────────────────────────────────────────────
# uv run 이 .venv 생성과 의존성 설치를 자동으로 처리합니다.
echo "[run.sh] 환경 준비 중..."
uv sync --quiet

echo "[run.sh] 파이프라인 실행"
exec uv run python main.py "$@"
