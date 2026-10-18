#!/usr/bin/env bash
# Spade -> Verilog -> LibreLane (sky130, in Docker) -> GLB + JSON for three.js.
# Usage: asic/run.sh <project>                 full flow
#        asic/run.sh <project> --export-only   only re-export the 3D model from the last run
# Extra args after the project (e.g. --z-scale 4) are passed to export_3d.py.
set -euo pipefail

ASIC_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ASIC_DIR"

usage() {
    echo "usage: asic/run.sh <project> [--export-only] [--z-scale K]" >&2
    echo "projects: $(ls projects | tr '\n' ' ')" >&2
    exit 1
}

project="${1:-}"
[[ -n "$project" && -f "projects/$project/config.json" ]] || usage
shift
proj="projects/$project"

export_only=0
export_args=()
for arg in "$@"; do
    if [[ "$arg" == "--export-only" ]]; then export_only=1; else export_args+=("$arg"); fi
done

if [[ ! -f .venv/.deps-installed ]] || [[ requirements.txt -nt .venv/.deps-installed ]]; then
    uv venv .venv --python 3.11 -q --allow-existing
    uv pip install -q --python .venv/bin/python -r requirements.txt
    touch .venv/.deps-installed
fi

# LibreLane's own --dockerized mode always mounts the whole home directory; run the
# image directly so the container only sees this project and the PDK cache.
LIBRELANE_IMAGE="ghcr.io/librelane/librelane:3.0.16"
PDK_ROOT="${PDK_ROOT:-$HOME/.ciel}"

run="$proj/runs/latest"
if (( ! export_only )); then
    (cd .. && swim build)
    cp ../build/spade.sv "$proj/spade.sv"
    rm -rf "$run"
    mkdir -p "$PDK_ROOT"
    proj_abs="$ASIC_DIR/$proj"
    docker run --rm -i \
        -v "$proj_abs:$proj_abs" \
        -v "$PDK_ROOT:$PDK_ROOT" -e "PDK_ROOT=$PDK_ROOT" -e PDK=sky130A \
        -w "$proj_abs" \
        "$LIBRELANE_IMAGE" \
        python3 -m librelane --pdk sky130A --run-tag latest config.json

    # Keep only what the export needs: final/ outputs and the resolved config.
    find "$run" -mindepth 1 -maxdepth 1 ! -name final ! -name resolved.json -exec rm -rf {} +
fi

[[ -d "$run/final" ]] || { echo "no run for '$project' yet; run without --export-only" >&2; exit 1; }
.venv/bin/python export_3d.py "$run" "$proj/out" ${export_args[@]+"${export_args[@]}"}
