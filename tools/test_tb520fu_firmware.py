"""Regression checks for the TB520FU QCA firmware namespace and service masks."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'tb520fu_installer', ROOT / 'scripts/install-tb520fu.py')
INSTALLER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALLER)


class FirmwareTest(unittest.TestCase):
    def test_qca_names_match_driver_requests(self):
        # The manifest contains DT names; btqca adds qca/ before requesting them.
        source = {
            'qcom/sm8650/lenovo/tb520fu/hmtbtfw20.tlv': b'patch',
            'qcom/sm8650/lenovo/tb520fu/hmtnv20_Lapis.bin': b'nvm',
            'qcom/sm8650/lenovo/tb520fu/other.bin': b'unchanged',
        }
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            archive = base / 'firmware.tar.gz'
            manifest = {}
            with tarfile.open(archive, 'w:gz') as tf:
                for name, data in source.items():
                    destination = 'usr/lib/firmware/' + name
                    member = tarfile.TarInfo(destination)
                    member.size = len(data)
                    tf.addfile(member, io.BytesIO(data))
                    manifest[name] = {
                        'destination': destination, 'size': len(data),
                        'sha256': hashlib.sha256(data).hexdigest(),
                    }
            (base / 'firmware-manifest.json').write_text(
                json.dumps({'files': manifest}))
            with patch.object(INSTALLER, 'DEVICE', base), patch.object(
                    INSTALLER, 'FIRMWARE_SHA',
                    hashlib.sha256(archive.read_bytes()).hexdigest()):
                payloads = INSTALLER.firmware(archive)
            prefix = 'usr/lib/firmware/steamos-arm/tb520fu/'
            self.assertEqual(payloads, {
                prefix + 'qca/qcom/sm8650/lenovo/tb520fu/hmtbtfw20.tlv': b'patch',
                prefix + 'qca/qcom/sm8650/lenovo/tb520fu/hmtnv20_Lapis.bin': b'nvm',
                prefix + 'qcom/sm8650/lenovo/tb520fu/other.bin': b'unchanged',
            })

    def test_masks_both_etc_layers_and_replaces_obsolete_paths(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / '.tb520fu-rootfs').touch()
            (root / 'usr/bin').mkdir(parents=True)
            (root / 'usr/bin/bash').write_bytes(b'fixture')
            prefix = 'usr/lib/firmware/steamos-arm/tb520fu/'
            old_name = 'qcom/sm8650/lenovo/tb520fu/hmtbtfw20.tlv'
            old = root / (prefix + old_name)
            old.parent.mkdir(parents=True)
            old.write_bytes(b'patch')
            payloads = {prefix + 'qca/' + old_name: b'patch'}
            for _ in range(2):
                INSTALLER.install(root, payloads, {})
            self.assertFalse(old.exists())
            self.assertEqual((root / (prefix + 'qca/' + old_name)).read_bytes(),
                             b'patch')
            for layer in ('etc', 'var/lib/overlays/etc/upper'):
                for unit in ('set-bluetooth-mac-address.service', 'scx.service'):
                    mask = root / layer / 'systemd/system' / unit
                    self.assertEqual(mask.readlink(), Path('/dev/null'))


if __name__ == '__main__':
    unittest.main()
