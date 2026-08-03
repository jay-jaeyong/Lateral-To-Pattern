#!/usr/bin/env bash
# images/ 아래 모델 폴더마다 각도별 플래그를 만들어 run.sh를 순차 실행합니다.
# 폴더에 있는 뷰만 플래그로 넘기고, 한 모델이 실패해도 다음 모델로 넘어갑니다.
set -uo pipefail

cd "$(dirname "$0")/.."

LOG_DIR="output/_runlogs"
mkdir -p "$LOG_DIR"

models=$(ls -d images/adidas_* images/asics_* images/nike_* 2>/dev/null | sort)
total=$(printf '%s\n' "$models" | grep -c . || true)
index=0
failed=()

for model_dir in $models; do
    index=$((index + 1))
    model=$(basename "$model_dir")

    args=()
    for view in lateral medial front heel top bottom; do
        for ext in webp jpg jpeg png; do
            candidate="$model_dir/$view.$ext"
            if [ -f "$candidate" ]; then
                args+=("--$view" "$candidate")
                break
            fi
        done
    done

    if [ ${#args[@]} -eq 0 ]; then
        echo "SKIP  [$index/$total] $model — 인식된 뷰 이미지 없음"
        continue
    fi

    # 이미 3스텝까지 끝난 모델은 건너뜁니다. 다시 돌리려면 해당 output 폴더를 지우세요.
    if compgen -G "output/$model/step_03_*_generated_*.png" > /dev/null; then
        echo "SKIP  [$index/$total] $model — 이미 완료됨"
        continue
    fi

    echo "START [$index/$total] $model — 뷰 $(( ${#args[@]} / 2 ))장"
    if ./run.sh "${args[@]}" > "$LOG_DIR/$model.log" 2>&1; then
        echo "OK    [$index/$total] $model"
    else
        echo "FAIL  [$index/$total] $model — $LOG_DIR/$model.log 확인"
        failed+=("$model")
    fi
done

echo "DONE  총 $total개 중 실패 ${#failed[@]}개"
if [ ${#failed[@]} -gt 0 ]; then
    printf '  실패: %s\n' "${failed[@]}"
fi
