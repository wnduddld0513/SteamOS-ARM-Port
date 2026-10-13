#!/bin/sh
# Activated only by the explicit diagnostic kernel argument.
case " $(cat /proc/cmdline) " in *" tb520fu.diagnostics=1 "*) ;; *) exit 0;; esac
export PATH=/usr/bin:/usr/sbin:/bin:/sbin
boot_id=$(cat /proc/sys/kernel/random/boot_id)
# /var/log is replaced by the SteamOS offload bind mount during boot.
# Keep capture on the root filesystem so that mount cannot hide its directory.
out=/tb520fu-boot-logs/$boot_id
mkdir -p "$out"
cat /proc/cmdline >"$out/cmdline.txt"
uname -a >"$out/kernel.txt"
# Each snapshot is bounded; preserve the last state after a forced power-off.
i=0
while [ "$i" -lt 90 ]; do
    dmesg >"$out/dmesg.txt.next" 2>&1
    mv "$out/dmesg.txt.next" "$out/dmesg.txt"
    {
        cat /proc/uptime
        systemctl --no-pager --plain --failed
        systemctl --no-pager --plain list-jobs
        ls -l /dev/dri /sys/class/graphics /sys/class/remoteproc
        for f in /sys/class/remoteproc/remoteproc*/state; do
            [ ! -r "$f" ] || { printf '%s: ' "$f"; cat "$f"; }
        done
        printf '\nDeferred devices:\n'
        cat /sys/kernel/debug/devices_deferred
        printf '\nBacklight state:\n'
        for f in /sys/class/backlight/*/brightness /sys/class/backlight/*/actual_brightness /sys/class/backlight/*/bl_power; do
            [ ! -r "$f" ] || { printf '%s: ' "$f"; cat "$f"; }
        done
        printf '\nDRM connectors:\n'
        for f in /sys/class/drm/card*-*/status /sys/class/drm/card*-*/enabled /sys/class/drm/card*-*/modes; do
            [ ! -r "$f" ] || { printf '%s: ' "$f"; cat "$f"; }
        done
        cat /proc/mounts
    } >"$out/state.txt" 2>&1
    journalctl -b --no-pager -n 3000 -o short-monotonic >"$out/journal.txt.next" 2>&1
    mv "$out/journal.txt.next" "$out/journal.txt"
    # Copy only after confirming /boot was actually mounted, never to its
    # underlying empty rootfs directory.
    if mountpoint -q /boot; then
        mkdir -p /boot/tb520fu-logs
        cp "$out/dmesg.txt" /boot/tb520fu-logs/dmesg.txt
        cp "$out/state.txt" /boot/tb520fu-logs/state.txt
        cp "$out/journal.txt" /boot/tb520fu-logs/journal.txt
        cp "$out/cmdline.txt" /boot/tb520fu-logs/cmdline.txt
    fi
    # EFI pstore may retain a panic from the previous failed boot. systemd
    # can move it to /var/lib/systemd/pstore, so collect from both locations.
    mkdir -p "$out/pstore"
    for dir in /sys/fs/pstore /var/lib/systemd/pstore; do
        [ ! -d "$dir" ] || cp -r "$dir"/. "$out/pstore"/ 2>/dev/null
    done
    if mountpoint -q /boot; then
        cp -r "$out/pstore" /boot/tb520fu-logs/
    fi
    sync
    i=$((i + 1))
    sleep 2
done
