#!/usr/bin/env bash
# Build Arch/SteamOS-native sensor, input and audio outputs in the dedicated rootfs.
# This is a future build recipe, not a validation command.
set -euo pipefail
source "$(dirname "$0")/tb520fu-common.sh"
r="$(tb520fu_rootfs "${1:?ROOTFS}")"
[[ "$(uname -m)" == aarch64 ]] || tb520fu_die "runtime build requires an ARM64 Linux host"
[[ "${EUID}" == 0 ]] || tb520fu_die "run runtime/image creation as root on the ARM64 build host"
source_repo="$(tb520fu_source)"
build="$r/opt/tb520fu-build"; mkdir -p "$build"
tb520fu_export "$source_repo" "$build/port" packages/tb321fu-sensors packages/inputplumber audio_topology
fetch_git() {
    local url="$1" rev="$2" name="$3" dest="$build/$3"
    [[ ! -e "$dest" ]] || tb520fu_die "runtime build directory exists: $dest (use a fresh rootfs)"
    git init -q "$dest"
    git -C "$dest" fetch -q --depth=1 "$url" "$rev"
    git -C "$dest" checkout -q --detach FETCH_HEAD
    [[ "$(git -C "$dest" rev-parse HEAD)" == "$rev" ]] || tb520fu_die "source pin mismatch: $name"
}
fetch_git https://github.com/GUF296/libssc "$TB520FU_LIBSSC_COMMIT" libssc
fetch_git https://github.com/GUF296/hexagonrpc "$TB520FU_HEXAGONRPC_COMMIT" hexagonrpc
fetch_git https://github.com/GUF296/iio-sensor-proxy "$TB520FU_SENSOR_PROXY_COMMIT" iio-sensor-proxy
fetch_git https://github.com/ShadowBlip/InputPlumber "$TB520FU_INPUTPLUMBER_COMMIT" inputplumber
fetch_git https://git.codelinaro.org/linaro/qcomlt/audioreach-topology.git "$TB520FU_TOPOLOGY_COMMIT" topology
fetch_git https://github.com/alsa-project/alsa-ucm-conf "$TB520FU_UCM_COMMIT" ucm
# The Pocket FIT polling fixes remain confined to this new binary; add the
# TB520FU IMU and Legion shortcut patches from the pinned source on top.
# Source patch 0006 builds on the sharing fix in 0001; preserve that order.
for p in "$build/port/packages/inputplumber/patches/"*.patch; do
    git -C "$build/inputplumber" apply "$p"
done
for p in "$TB520FU_REPO_ROOT/external-and-mods/InputPlumber/"000[12]-*.patch; do
    git -C "$build/inputplumber" apply "$p"
done
patch -d "$build/libssc" -p1 -F0 < "$build/port/packages/tb321fu-sensors/specs/libssc-0001-max-sample-rate.patch"
sed -i -e 's#Y700_REGISTRY_ROOT#QCOM_SNS_REGISTRY_ROOT#g' \
    -e 's#/var/lib/y700-sns/persist/sensors/registry#/var/lib/qcom-sns/persist/sensors/registry#g' "$build/hexagonrpc/hexagonrpcd/apps_std.c"
# Build against the target libc, never copy Fedora RPMs into Arch/SteamOS.
mounted=()
cleanup() { local m; for ((i=${#mounted[@]}-1;i>=0;i--)); do umount "${mounted[$i]}"; done; }
trap cleanup EXIT
for d in proc sys dev; do
    mkdir -p "$r/$d"
    mount --bind "/$d" "$r/$d"
    mounted+=("$r/$d")
done
chroot "$r" /usr/bin/bash -euo pipefail <<'BUILD'
pacman -S --needed --noconfirm base-devel git meson ninja glib2 libqmi protobuf-c protobuf \
    libgudev polkit systemd libxml2 libiio libusb rust cargo clang alsa-utils
cd /opt/tb520fu-build
stage=/opt/tb520fu-runtime-stage
mkdir -p "$stage"
mbuild() {
    local src="$1"; shift
    meson setup "$src/build" "$src" --prefix=/usr --libdir=lib --libexecdir=libexec --buildtype=release "$@"
    meson compile -C "$src/build"
    DESTDIR="$stage" meson install -C "$src/build"
}
mbuild libssc
# Headers and libraries only inside this dedicated build rootfs.
cp -a "$stage/usr/." /usr/
ldconfig
mbuild hexagonrpc
mbuild iio-sensor-proxy -Dssc-support=enabled -Dtests=false -Dgtk-tests=false -Dgtk_doc=false
mkdir -p "$stage/usr/libexec"
cc -O2 -Wall -o "$stage/usr/libexec/tb321fu-imu-bridge" \
    port/packages/tb321fu-sensors/bridge/tb321fu-imu-bridge.c \
    $(pkg-config --cflags --libs libssc glib-2.0 gobject-2.0) -lm
(cd inputplumber && cargo build --bin inputplumber --release --locked -j"${BUILD_JOBS:-4}")
install -Dm0755 inputplumber/target/release/inputplumber "$stage/usr/bin/inputplumber"
# InputPlumber's stock capability maps remain available; add the TB520FU map later.
cp -a inputplumber/rootfs/usr/. "$stage/usr/"
# Build and namespace the topology and codec sequences to this tablet.
m4 -I topology -I port/audio_topology port/audio_topology/SM8650-TB520FU.m4 > TB520FU.conf
alsatplg -c TB520FU.conf -o TB520FU-tplg.bin
install -Dm0644 TB520FU-tplg.bin "$stage/usr/lib/firmware/steamos-arm/tb520fu/qcom/sm8650/Lenovo-Yoga-TB520FU-tplg.bin"
u="$stage/usr/share/alsa/ucm2/Qualcomm/sm8650/TB520FU"
mkdir -p "$u"
cp -a ucm/ucm2/codecs "$u/"
find "$u/codecs" -type f -name '*.conf' -exec sed -i 's|"/codecs/|"/Qualcomm/sm8650/TB520FU/codecs/|g' {} +
# No unscoped daemon units from the build dependencies.
rm -f "$stage"/usr/lib/systemd/system/hexagonrpcd-*.service
BUILD
# Some upstream Meson projects place the proxy in libexec; verify that
# contract and all runtime hashes before this stage can be installed.
python3 - "$r/opt/tb520fu-runtime-stage" "$TB520FU_SOURCE_COMMIT" <<'PY'
from pathlib import Path
import hashlib, json, sys
stage=Path(sys.argv[1]); files={}
for p in sorted(stage.rglob('*')):
    name=p.relative_to(stage).as_posix()
    if p.is_symlink():
        if p.readlink().is_absolute() or not p.resolve().is_relative_to(stage.resolve()):
            raise SystemExit('unsafe runtime symlink: '+name)
        files[name]={'link':p.readlink().as_posix()}
    elif p.is_file():
        data=p.read_bytes()
        files[name]={'sha256':hashlib.sha256(data).hexdigest(),'size':len(data),'mode':p.stat().st_mode & 0o777}
(stage/'TB520FU-RUNTIME.json').write_text(json.dumps({'source_commit':sys.argv[2],'files':files},indent=2)+'\n')
PY
echo "TB520FU runtime stage: $r/opt/tb520fu-runtime-stage"
