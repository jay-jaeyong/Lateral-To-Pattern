#!/usr/bin/env bash
# inputs/photos/ 아래 신발 폴더들을 병렬로 실행합니다.
#
# 사용법:
#   scripts/run_parallel.sh                        # 모든 신발, 모든 서비스
#   scripts/run_parallel.sh color_pattern          # color_pattern만
#   scripts/run_parallel.sh --jobs 2 --repeat 3
#   JOBS=6 REPEAT=3 scripts/run_parallel.sh
#
# sketch_pattern은 이 스크립트로 단독 실행할 수 없습니다. 이 스크립트는
# inputs/photos/*/ (신발 사진 폴더)만 훑는데, sketch_pattern의 입력은
# 컬러 패턴 파일(또는 그 폴더)이기 때문입니다. sketch_pattern은
# scripts/run_service.py sketch_pattern --input <컬러 패턴 파일 또는 폴더>
# 를 직접 쓰세요.
#
# run.sh를 쓰지 않고 venv 파이썬을 직접 부릅니다. run.sh는 매번 uv sync를
# 하는데, 동시에 여러 개가 돌면 venv 락을 두고 경쟁합니다.
set -uo pipefail

cd "$(dirname "$0")/.."

PY=${PY:-.venv/bin/python}
JOBS=${JOBS:-4}
REPEAT=${REPEAT:-1}
LOG_DIR=outputs/_runlogs
mkdir -p "$LOG_DIR"

is_positive_int() {
    case "$1" in
        ''|*[!0-9]*) return 1 ;;
        # 선행 0은 거부한다. "00"은 여기를 통과해도 [ n -ge 00 ] 비교에서
        # 0으로 평가돼 동시 실행 수 0으로 무한 대기에 빠진다.
        0*) return 1 ;;
        *) return 0 ;;
    esac
}

services=()
while [ $# -gt 0 ]; do
    case "$1" in
        --jobs)
            if [ $# -lt 2 ]; then
                echo "--jobs 뒤에 값이 필요합니다." >&2
                exit 1
            fi
            JOBS="$2"
            shift 2
            ;;
        --repeat)
            if [ $# -lt 2 ]; then
                echo "--repeat 뒤에 값이 필요합니다." >&2
                exit 1
            fi
            REPEAT="$2"
            shift 2
            ;;
        --*)
            echo "알 수 없는 옵션: $1" >&2
            exit 1
            ;;
        *)
            services+=("$1")
            shift
            ;;
    esac
done

if ! is_positive_int "$JOBS"; then
    echo "--jobs는 1 이상의 정수여야 합니다: $JOBS" >&2
    exit 1
fi
if ! is_positive_int "$REPEAT"; then
    echo "--repeat는 1 이상의 정수여야 합니다: $REPEAT" >&2
    exit 1
fi

if [ ${#services[@]} -gt 0 ]; then
    for svc in "${services[@]}"; do
        case "$svc" in
            sketch_pattern)
                echo "run_parallel.sh는 inputs/photos/ 아래 신발 폴더를 훑습니다." \
                     "sketch_pattern의 입력은 컬러 패턴 파일(또는 그 폴더)이라서" \
                     "이 스크립트로 단독 병렬 실행할 수 없습니다." \
                     "scripts/run_service.py sketch_pattern --input <경로>를 직접 쓰세요." >&2
                exit 1
                ;;
            color_pattern)
                ;;
            *)
                echo "알 수 없는 서비스: $svc (지원: color_pattern)" >&2
                exit 1
                ;;
        esac
    done
fi

run_one() {
    local shoe_dir=$1
    local label
    label=$(basename "$shoe_dir")

    if [ ${#services[@]} -eq 0 ]; then
        $PY scripts/run_all.py --input "$shoe_dir" --repeat "$REPEAT" \
            > "$LOG_DIR/${label}.log" 2>&1 \
            && echo "OK   $label" || echo "FAIL $label"
        return
    fi

    local svc
    for svc in "${services[@]}"; do
        $PY scripts/run_service.py "$svc" --input "$shoe_dir" --repeat "$REPEAT" \
            > "$LOG_DIR/${label}_${svc}.log" 2>&1 \
            && echo "OK   $label $svc" || echo "FAIL $label $svc"
    done
}

shopt -s nullglob
targets=(inputs/photos/*/)
if [ ${#targets[@]} -eq 0 ]; then
    echo "inputs/photos/ 아래에 신발 폴더가 없습니다."
    exit 1
fi

echo "START ${#targets[@]}개 신발, 동시 ${JOBS}개, 반복 ${REPEAT}회"
for shoe_dir in "${targets[@]}"; do
    while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do
        wait -n 2>/dev/null || sleep 1
    done
    run_one "${shoe_dir%/}" &
done
wait
echo "DONE"
