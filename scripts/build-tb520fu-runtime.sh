#!/usr/bin/env bash
# Build Arch/SteamOS-native sensor, input and audio outputs in the dedicated rootfs.
# Runs natively on ARM64, or inside an ARM64 rootfs using host binfmt/QEMU.
set -euo pipefail
source "$(dirname "$0")/tb520fu-common.sh"
r="$(tb520fu_rootfs "${1:?ROOTFS}")"
[[ "${EUID}" == 0 ]] || tb520fu_die "run runtime/image creation as root"
# Fail before downloads if the host cannot execute the target architecture.
readelf -h "$r/usr/bin/bash" | grep -q 'Machine:.*AArch64' || tb520fu_die "rootfs is not ARM64"
[[ "$(chroot "$r" /usr/bin/uname -m)" == aarch64 ]] || tb520fu_die "ARM64 execution unavailable; install/register qemu-user-static binfmt on x86 hosts"
export BUILD_JOBS="${BUILD_JOBS:-2}"
source_repo="$(tb520fu_source)"
build="$r/opt/tb520fu-build"; mkdir -p "$build"
tb520fu_export "$source_repo" "$build/port" packages/tb321fu-sensors packages/inputplumber audio_topology
fetch_git() {
    local url="$1" rev="$2" name="$3" dest="$build/$3"
    if [[ -e "$dest" ]]; then
        if git -C "$dest" rev-parse --verify HEAD >/dev/null 2>&1; then
            [[ "$(git -C "$dest" rev-parse HEAD)" == "$rev" ]] || tb520fu_die "source pin mismatch: $name"
            return
        fi
        [[ -d "$dest/.git" && -z "$(git -C "$dest" status --porcelain)" ]] || tb520fu_die "incomplete source cache is not empty: $name"
    fi
    local upload_pack=()
    if [[ "$name" == topology && -n "${TB520FU_TOPOLOGY_DIR:-}" ]]; then
        url="$TB520FU_TOPOLOGY_DIR"
        # Apply trust to the local upload-pack process, confined to this path.
        # Client-side safe.directory is not inherited by upload-pack.
        local command
        printf -v command 'git -c safe.directory=%q -c safe.directory=%q upload-pack' "$url" "$url/.git"
        upload_pack=(--upload-pack="$command")
    fi
    git init -q "$dest"
    git -C "$dest" fetch -q --depth=1 "${upload_pack[@]}" "$url" "$rev"
    git -C "$dest" checkout -q --detach FETCH_HEAD
    [[ "$(git -C "$dest" rev-parse HEAD)" == "$rev" ]] || tb520fu_die "source pin mismatch: $name"
}
fetch_git https://github.com/GUF296/libssc "$TB520FU_LIBSSC_COMMIT" libssc
fetch_git https://github.com/GUF296/hexagonrpc "$TB520FU_HEXAGONRPC_COMMIT" hexagonrpc
fetch_git https://github.com/GUF296/iio-sensor-proxy "$TB520FU_SENSOR_PROXY_COMMIT" iio-sensor-proxy
fetch_git https://github.com/ShadowBlip/InputPlumber "$TB520FU_INPUTPLUMBER_COMMIT" inputplumber
fetch_git https://git.codelinaro.org/linaro/qcomlt/audioreach-topology.git "$TB520FU_TOPOLOGY_COMMIT" topology
fetch_git https://github.com/alsa-project/alsa-ucm-conf "$TB520FU_UCM_COMMIT" ucm
# Recreate tracked patch inputs on resume; later patches can change an earlier
# patch's reverse context. This is our dedicated clone; keep Cargo's output.
git -C "$build/inputplumber" reset --hard "$TB520FU_INPUTPLUMBER_COMMIT"
git -C "$build/inputplumber" clean -fd -e target/
# The Pocket FIT polling fixes remain confined to this new binary; add the
# TB520FU IMU and Legion shortcut patches from the pinned source on top.
# Source patch 0006 builds on the sharing fix in 0001; preserve that order.
for p in "$build/port/packages/inputplumber/patches/"*.patch; do
    git -C "$build/inputplumber" apply "$p"
done
for p in "$TB520FU_REPO_ROOT/external-and-mods/InputPlumber/"000[12]-*.patch; do
    git -C "$build/inputplumber" apply "$p"
done
for p in "$build/port/packages/tb321fu-sensors/specs/"libssc-*.patch; do
    if ! git -C "$build/libssc" apply --reverse --check "$p" 2>/dev/null; then
        git -C "$build/libssc" apply "$p"
    fi
done
sed -i -e 's#Y700_REGISTRY_ROOT#QCOM_SNS_REGISTRY_ROOT#g' \
    -e 's#/var/lib/y700-sns/persist/sensors/registry#/var/lib/qcom-sns/persist/sensors/registry#g' "$build/hexagonrpc/hexagonrpcd/apps_std.c"
# Frame's packaged Cargo is too old for the pinned version-4 Cargo.lock.
# Install only compiler/Cargo/target stdlib in the excluded build directory.
rust_name="rust-$TB520FU_RUST_VERSION-aarch64-unknown-linux-gnu"
rust_archive="${STEAMOS_WORK:-/work/tb520fu}/cache/$rust_name.tar.xz"
mkdir -p "$(dirname "$rust_archive")"
if [[ ! -f "$rust_archive" ]] || ! echo "$TB520FU_RUST_SHA256  $rust_archive" | sha256sum -c --quiet; then
    curl -fL --retry 3 "https://static.rust-lang.org/dist/$rust_name.tar.xz" -o "$rust_archive.part"
    echo "$TB520FU_RUST_SHA256  $rust_archive.part" | sha256sum -c --quiet
    mv "$rust_archive.part" "$rust_archive"
fi
if [[ ! -f "$build/$rust_name/install.sh" ]]; then
    tar -xf "$rust_archive" -C "$build" --exclude="$rust_name/rust-docs*"
fi
# Build against the target libc, never copy Fedora RPMs into Arch/SteamOS.
# Resolve DNS inside the staging filesystem, replacing only its leaf symlink.
rm -f "$r/etc/resolv.conf"
install -m0644 /etc/resolv.conf "$r/etc/resolv.conf"
mounted=()
cleanup() { local m; for ((i=${#mounted[@]}-1;i>=0;i--)); do umount "${mounted[$i]}"; done; }
trap cleanup EXIT
for d in proc sys dev; do
    mkdir -p "$r/$d"
    mount --bind "/$d" "$r/$d"
    mounted+=("$r/$d")
done
chroot "$r" /usr/bin/env BUILD_JOBS="$BUILD_JOBS" TB520FU_RUST_VERSION="$TB520FU_RUST_VERSION" /usr/bin/bash -euo pipefail <<'BUILD'
# Some applications in the base release have hand-written package records.
# An empty file list accurately preserves their unowned/manual installation.
for record in /usr/lib/holo/pacmandb/local/*; do
    [[ -d "$record" ]] || continue
    [[ -f "$record/files" ]] || printf '%%FILES%%\n' > "$record/files"
done
pacman -S --needed --noconfirm --overwrite 'usr/include/iio.h,usr/lib/libiio.so*,usr/lib/pkgconfig/libiio.pc' base-devel git meson ninja glib2 libqmi protobuf-c protobuf \
    libgudev polkit systemd libxml2 libusb clang alsa-utils gobject-introspection
if ! pkg-config --exists libiio; then pacman -S --needed --noconfirm libiio; fi
cd /opt/tb520fu-build
# Frame hotfixes contain new Abseil while the archived protobuf-c generator
# still needs the 2401 ABI. Keep those compatibility libraries build-local;
# never replace the newer libraries used by the desktop/Steam runtime.
if ldd /usr/bin/protoc-gen-c | grep -q 'libabsl_.*not found'; then
    mkdir -p compat-cache compat-libs compat-extract
    pacman -Sw --noconfirm --nodeps --cachedir "$PWD/compat-cache" extra/abseil-cpp
    for archive in compat-cache/abseil-cpp-20240116.1-1-aarch64.pkg.tar.*; do
        [[ "$archive" != *.sig ]] || continue
        bsdtar -xf "$archive" -C compat-extract usr/lib
    done
    cp -a compat-extract/usr/lib/libabsl_*.so.2401.0.0 compat-libs/
fi
# The hotfix also replaced libprotobuf.so.25 without rebuilding its generator.
# Use the archived generator's matching libraries only while compiling.
if [[ ! -f compat-libs/libprotoc.so.25.3.0 ]]; then
    mkdir -p compat-cache compat-libs compat-extract
    pacman -Sw --noconfirm --nodeps --cachedir "$PWD/compat-cache" extra/protobuf
    for archive in compat-cache/protobuf-25.3-*-aarch64.pkg.tar.*; do
        [[ "$archive" != *.sig ]] || continue
        bsdtar -xf "$archive" -C compat-extract usr/lib
    done
    cp -a compat-extract/usr/lib/libproto*.so* compat-libs/
fi
export LD_LIBRARY_PATH="/opt/tb520fu-build/compat-libs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
if [[ ! -x rust-toolchain/bin/cargo ]]; then
    bash "rust-$TB520FU_RUST_VERSION-aarch64-unknown-linux-gnu/install.sh" \
        --prefix=/opt/tb520fu-build/rust-toolchain \
        --components=rustc,cargo,rust-std-aarch64-unknown-linux-gnu --disable-ldconfig
fi
export PATH="/opt/tb520fu-build/rust-toolchain/bin:$PATH"
rustc --version; cargo --version
stage=/opt/tb520fu-runtime-stage
mkdir -p "$stage"
mbuild() {
    local src="$1"; shift
    local reconfigure=()
    [[ ! -f "$src/build/build.ninja" ]] || reconfigure=(--reconfigure)
    meson setup "${reconfigure[@]}" "$src/build" "$src" --prefix=/usr --libdir=lib --libexecdir=libexec --buildtype=release "$@"
    meson compile -C "$src/build" -j"$BUILD_JOBS"
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
