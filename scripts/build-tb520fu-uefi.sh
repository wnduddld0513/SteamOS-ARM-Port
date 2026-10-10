#!/usr/bin/env bash
# Explicit UEFI source preparation / optional future compilation. No flashing.
set -euo pipefail
source "$(dirname "$0")/tb520fu-common.sh"
mode="${1:---prepare-only}" stock="${2:-${TB520FU_STOCK_DIR:-}}"
case "$mode" in
    --help|-h) echo "Usage: $0 --prepare-only|--build|--build-debug STOCK_IMAGE_DIRECTORY"; exit 0;;
    --prepare-only|--build|--build-debug) ;;
    *) tb520fu_die "use --prepare-only, --build or --build-debug";;
esac
[[ -d "$stock" ]] || tb520fu_die "provide TB520FU stock image/ directory"
work="${STEAMOS_WORK:-/work/tb520fu}/uefi"
mkdir -p "$work"
# Isolated new checkout. Never update another device's UEFI checkout.
mu="$(mktemp -d "$work/mu-tb520fu.XXXXXX")"
lock="$TB520FU_REPO_ROOT/external-and-mods/tb520fu/uefi/source-lock.json"
readarray -t pin < <(python3 - "$lock" <<'PY'
import json, sys
lock = json.load(open(sys.argv[1]))
print(lock['mu_url'])
print(lock['mu_commit'])
PY
)
git -C "$mu" init -q
git -C "$mu" remote add origin "${pin[0]}"
git -C "$mu" fetch --depth=1 origin "${pin[1]}"
git -C "$mu" checkout -q --detach FETCH_HEAD
# No binary artifacts from other devices and no upstream push from this checkout.
git -C "$mu" remote set-url --push origin DISABLED
# Preparation and the platform DSC need the pinned submodules (Mu_Basecore for the
# dispatcher trace patch, mu_plus and the OEM sample for the platform sources).
# Borrow objects from a sibling checkout when one is already present.
ref=()
for prev in "$work"/mu-tb520fu.*; do
    [[ "$prev" == "$mu" ]] && continue
    [[ -e "$prev/Mu_Basecore/.git" ]] || continue
    ref=(--reference "$prev"); break
done
git -c safe.directory="$mu" -C "$mu" submodule update --init --recursive --depth 1 ${ref[@]+"${ref[@]}"}
python3 "$TB520FU_REPO_ROOT/scripts/prepare-tb520fu-uefi.py" --mu "$mu" --stock "$stock"
if [[ "$mode" == --prepare-only ]]; then
    echo "Prepared only (no compiler invoked): $mu"
    echo "Future build: cd '$mu'; python3 build_uefi.py -d tb520fu -r RELEASE"
    exit 0
fi
# Requires the pinned project's documented toolchain and pip dependencies.
# build_uefi.py handles its own pinned Mu source submodules; never pass --update.
build_type=RELEASE; suffix=""
if [[ "$mode" == --build-debug ]]; then build_type=DEBUG; suffix="-debug"; fi
(cd "$mu" && python3 build_uefi.py -d tb520fu -r "$build_type")
image="$mu/Mu-tb520fu.img"
[[ -s "$image" ]] || tb520fu_die "Mu-tb520fu.img was not produced"
out="$work/output"; mkdir -p "$out"
install -m0644 "$image" "$out/tb520fu-uefi-boot${suffix}.img"
install -m0644 "$mu/TB520FU-PREPARED.json" "$out/UEFI-SOURCE.json"
python3 - "$out" "$lock" "$build_type" "$suffix" <<'PY'
import hashlib, json, sys
from pathlib import Path
out = Path(sys.argv[1]); image = out / ('tb520fu-uefi-boot' + sys.argv[4] + '.img')
lock = json.load(open(sys.argv[2]))
(out / 'boot-image.json').write_text(json.dumps({
    'device': 'TB520FU', 'mu_commit': lock['mu_commit'],
    'stock_inputs': lock['stock'], 'sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
    'compiled': True, 'boot_tested': False, 'build_type': sys.argv[3]
}, indent=2) + '\n')
PY
(cd "$out" && sha256sum "tb520fu-uefi-boot${suffix}.img" UEFI-SOURCE.json boot-image.json > SHA256SUMS)
echo "Experimental TB520FU UEFI generated: $out; boot not tested"
