#!/usr/bin/env python3
"""Keep Linux from taking ownership of the firmware display during diagnosis."""

import shutil
import subprocess
from pathlib import Path


DISABLED_NODES = (
    '/soc@0/display-subsystem@ae00000',
    '/soc@0/clock-controller@af00000',
    '/soc@0/geniqup@ac0000/i2c@a98000/backlight@11',
    '/soc@0/geniqup@ac0000/i2c@a9c000/backlight@11',
    # These are root nodes, outside MDSS. fixed.c otherwise requests their
    # GPIOs as OUT_LOW even with regulator_ignore_unused on the command line.
    '/regulator-panel-enp',
    '/regulator-panel-enn',
)


def _disable_nodes(source: Path, destination: Path, nodes: tuple[str, ...]) -> None:
    if source.resolve() == destination.resolve():
        raise ValueError('The diagnostic DTB must be separate from the native DTB')
    shutil.copyfile(source, destination)
    for node in nodes:
        # Fail on a renamed/missing node rather than silently making an
        # incomplete diagnostic tree.
        subprocess.run(['fdtget', '-p', str(destination), node],
                       check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['fdtput', '-t', 's', str(destination), node,
                        'status', 'disabled'], check=True)
    for node in nodes:
        status = subprocess.check_output(
            ['fdtget', '-t', 's', str(destination), node, 'status'], text=True)
        if status.strip() != 'disabled':
            raise RuntimeError(f'{node} is still enabled')


def make_firmware_display_dtb(source: Path, destination: Path) -> None:
    _disable_nodes(source, destination, DISABLED_NODES)


def make_internal_display_dtb(source: Path, destination: Path) -> None:
    # Keep dual DSI active; an unavailable DP bridge must not defer the entire
    # MSM component master during internal panel bring-up.
    _disable_nodes(source, destination, (
        '/soc@0/display-subsystem@ae00000/displayport-controller@af54000',
    ))
