#!/usr/bin/env python3
"""Test internal-image module pairing without mounts, compilers or device access."""
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'internal_image', ROOT / 'scripts/build-tb520fu-internal.py')
internal_image = importlib.util.module_from_spec(spec)
spec.loader.exec_module(internal_image)


class KernelPairingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='tb520fu-pairing-')
        self.addCleanup(self.temp.cleanup)
        base = Path(self.temp.name)
        self.root = base / 'root'
        self.kout = base / 'kernel'
        release = '7.2.6-tb520fu-steamos'
        self.expected = self.kout / 'modules' / release
        self.installed = self.root / 'usr/lib/modules' / release
        self.expected.mkdir(parents=True)
        (self.kout / 'boot').mkdir()
        (self.kout / 'boot/Image').write_bytes(b'new kernel')
        (self.expected / 'vmlinuz').write_bytes(b'new kernel')
        (self.expected / 'test.ko').write_bytes(b'new module with matching BTF')
        shutil.copytree(self.expected, self.installed)

    def test_matching_payload(self):
        internal_image.verify_kernel_modules(self.root, self.kout)

    def test_stale_module_with_matching_carrier(self):
        (self.installed / 'test.ko').write_bytes(b'old module BTF')
        with self.assertRaisesRegex(ValueError, 'installed modules differ'):
            internal_image.verify_kernel_modules(self.root, self.kout)

    def test_missing_and_extra_modules(self):
        (self.installed / 'test.ko').unlink()
        with self.assertRaisesRegex(ValueError, 'installed modules differ'):
            internal_image.verify_kernel_modules(self.root, self.kout)
        shutil.copy2(self.expected / 'test.ko', self.installed / 'test.ko')
        (self.installed / 'stale.ko').write_bytes(b'unexpected module')
        with self.assertRaisesRegex(ValueError, 'installed modules differ'):
            internal_image.verify_kernel_modules(self.root, self.kout)

    def test_inconsistent_kernel_output(self):
        (self.kout / 'boot/Image').write_bytes(b'different kernel')
        with self.assertRaisesRegex(ValueError, 'module carrier'):
            internal_image.verify_kernel_modules(self.root, self.kout)


if __name__ == '__main__':
    unittest.main()
