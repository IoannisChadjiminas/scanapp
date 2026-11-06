"""Local candidate runs: mounts, fingerprints and skipped gates."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import local_candidate as lc


class LocalCandidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        data = self.tmp / 'data'
        for sub in ('models', 'reference-images', 'features/enfive'):
            (data / sub).mkdir(parents=True)
        (data / 'catalog.sqlite').write_text('')
        (data / 'features/enfive/manifest.json').write_text('{"cards": 1}')
        self.release = self.tmp / 'cand.env'
        self.release.write_text('PLANETSCALE_SCHEMA=s\nPLANETSCALE_IMPORT_ID=PS-1\n'
                                'REFERENCE_FEATURES_DIR=/data/features/enfive\n')
        self.config = dict(data_dir=str(data), compose_env=None)

    def test_api_owned_files_stay_writable(self):
        mounts = lc.data_mounts(self.tmp / 'data')
        targets = [m.split(':')[1] for m in mounts]
        self.assertEqual(targets, ['/data/features', '/data/models', '/data/reference-images'])
        self.assertTrue(all(m.endswith(':ro') for m in mounts))

    def test_feature_manifest_change_changes_fingerprint(self):
        before = lc.fingerprint(self.config, self.release)['all']
        (self.tmp / 'data/features/enfive/manifest.json').write_text('{"cards": 2}')
        self.assertNotEqual(before, lc.fingerprint(self.config, self.release)['all'])

    def test_passed_gate_with_same_inputs_is_skipped(self):
        with mock.patch.object(lc, 'STATE', self.tmp / 'state'):
            candidate = lc.Candidate('enfive')
            candidate.dir.mkdir(parents=True)
            candidate.record('panel:review', 'k1', True, {})
            self.assertTrue(candidate.already('panel:review', 'k1', force=False))
            self.assertFalse(candidate.already('panel:review', 'k2', force=False))
            self.assertFalse(candidate.already('panel:review', 'k1', force=True))
            with self.assertRaises(SystemExit):
                candidate.record('panel:review', 'k3', False, {})
            self.assertFalse(candidate.already('panel:review', 'k3', force=False))

    def test_sizes(self):
        self.assertEqual(lc.parse_bytes('1.5GiB'), 1610612736)
        self.assertEqual(lc.parse_bytes('512MiB'), 512 * 1024**2)
        self.assertEqual(lc.limit_bytes('2147483648'), 2 * 1024**3)
        self.assertEqual(lc.limit_bytes('4g'), 4 * 1024**3)
        self.assertEqual(lc.host_path('/data/features/x', Path('/d')), Path('/d/features/x'))
        self.assertIsNone(lc.host_path('/srv/x', Path('/d')))


if __name__ == '__main__':
    unittest.main()
