#!/usr/bin/env bash
# 지정한 모델들을 병렬로 실행합니다. 모델당 2회, 각 회차는 순차입니다.
#
# run.sh를 쓰지 않고 venv 파이썬을 직접 부릅니다. run.sh는 매번 `uv sync`를
# 하는데, 동시에 여러 개가 돌면 venv 락을 두고 경쟁합니다.
set -uo pipefail

cd "$(dirname "$0")/.."

PY=.venv/bin/python
RUNS=${RUNS:-2}          # 모델당 실행 횟수
JOBS=${JOBS:-4}          # 동시에 돌릴 모델 수
VER=${VER:-v6}           # 출력 폴더 접미사. RUNS=1이면 {모델}_{VER}, 아니면 {모델}_{VER}-N
LOG_DIR=output/_runlogs
mkdir -p "$LOG_DIR"

run_model() {
    local m=$1
    local args=()
    local v e
    for v in lateral medial front heel top bottom; do
        for e in webp jpg jpeg png; do
            if [ -f "images/$m/$v.$e" ]; then
                args+=("--$v" "images/$m/$v.$e")
                break
            fi
        done
    done

    if [ ${#args[@]} -eq 0 ]; then
        echo "SKIP $m — 인식된 뷰 이미지 없음"
        return
    fi

    local n label
    for n in $(seq 1 "$RUNS"); do
        if [ "$RUNS" -eq 1 ]; then label="${m}_${VER}"; else label="${m}_${VER}-${n}"; fi
        if $PY main.py --run-label "$label" "${args[@]}" > "$LOG_DIR/${label}.log" 2>&1; then
            echo "OK   $label"
        else
            echo "FAIL $label"
        fi
    done
}

models=("$@")
if [ ${#models[@]} -eq 0 ]; then
    echo "사용법: $0 <모델명> [모델명...]"
    exit 1
fi

echo "START ${#models[@]}개 모델 × ${RUNS}회, 동시 ${JOBS}개, 접미사 ${VER}"
for m in "${models[@]}"; do
    while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do
        wait -n 2>/dev/null || sleep 1
    done
    run_model "$m" &
done
wait
echo "DONE"
