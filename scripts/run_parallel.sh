#!/usr/bin/env bash
# inputs/photos/ 아래 신발 폴더들을 병렬로 실행합니다.
#
# 사용법:
#   scripts/run_parallel.sh                        # 모든 신발, 모든 서비스
#   scripts/run_parallel.sh sketch_pattern         # 스케치만
#   JOBS=6 REPEAT=3 scripts/run_parallel.sh
#
# run.sh를 쓰지 않고 venv 파이썬을 직접 부릅니다. run.sh는 매번 uv sync를
# 하는데, 동시에 여러 개가 돌면 venv 락을 두고 경쟁합니다.
set -uo pipefail

cd "$(dirname "$0")/.."

PY=.venv/bin/python
JOBS=${JOBS:-4}
REPEAT=${REPEAT:-1}
LOG_DIR=outputs/_runlogs
mkdir -p "$LOG_DIR"

services=("$@")

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
