#!/usr/bin/env bash
# Sourced only by the opt-in TB520FU entry points.
TB520FU_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$TB520FU_REPO_ROOT/external-and-mods/tb520fu/source.env"
tb520fu_die() { echo "TB520FU: $*" >&2; exit 1; }
tb520fu_source() {
    local cache="${TB520FU_SOURCE_CACHE:-${STEAMOS_WORK:-/work/tb520fu}/source-cache}"
    if [[ -n "${TB520FU_SOURCE_DIR:-}" ]]; then
        cache="$TB520FU_SOURCE_DIR"
        # Export always archives the exact pin, even if a later README commit
        # has advanced the local branch. Working-tree contents are never copied.
        git -c safe.directory="$cache" -C "$cache" cat-file -e "$TB520FU_SOURCE_COMMIT^{commit}" || tb520fu_die "pinned source commit missing from local repository"
        [[ -z "$(git -c safe.directory="$cache" -C "$cache" status --porcelain --untracked-files=no)" ]] || tb520fu_die "source has tracked modifications"
    else
        if [[ ! -d "$cache/.git" ]]; then
            mkdir -p "$cache"
            git -c safe.directory="$cache" -C "$cache" init -q >&2
            git -c safe.directory="$cache" -C "$cache" remote add origin "$TB520FU_SOURCE_URL"
        fi
        [[ "$(git -c safe.directory="$cache" -C "$cache" remote get-url origin)" == "$TB520FU_SOURCE_URL" ]] || tb520fu_die "unexpected source cache remote"
        git -c safe.directory="$cache" -C "$cache" cat-file -e "$TB520FU_SOURCE_COMMIT^{commit}" 2>/dev/null ||
            git -c safe.directory="$cache" -C "$cache" fetch --depth=1 origin "$TB520FU_SOURCE_COMMIT" >&2
    fi
    printf '%s\n' "$cache"
}
tb520fu_export() {
    local source="$1" dest="$2"; shift 2
    mkdir -p "$dest"
    git -c safe.directory="$source" -C "$source" archive "$TB520FU_SOURCE_COMMIT" "$@" | tar -x -C "$dest"
}
tb520fu_rootfs() {
    local root
    root="$(realpath -e "${1:?rootfs}")"
    [[ "$root" != / && -d "$root/usr/bin" ]] || tb520fu_die "not a staging rootfs"
    [[ -f "$root/.tb520fu-rootfs" ]] || tb520fu_die "rootfs is not owned by the TB520FU image builder"
    printf '%s\n' "$root"
}
