# -*- coding: utf-8 -*-
import hashlib
import json
import pathlib
import sys
import tempfile
import types
import unittest
import zipfile


from _paths import ROOT, SRC, project_file  # noqa: E402
sys.modules.setdefault('pyodbc', types.SimpleNamespace())

import backup
import restore_backup


def make_archive(path, info, files):
    archive_files = []
    for name, data in files.items():
        archive_files.append({'name': name, 'sha256': hashlib.sha256(data).hexdigest()})
    info = dict(info, archive_files=archive_files)
    with zipfile.ZipFile(path, 'w') as z:
        for name, data in files.items():
            z.writestr(name, data)
        z.writestr('manifest.json', json.dumps(info))


class BackupTests(unittest.TestCase):
    def test_archive_hash_verification(self):
        with tempfile.TemporaryDirectory() as td:
            good = pathlib.Path(td) / 'good.taskhubbackup'
            make_archive(good, {'kind': 'FULL', 'attachments': []}, {'database/x.bak': b'database'})
            self.assertEqual(backup.verify_archive(good), (True, []))
            bad = pathlib.Path(td) / 'bad.taskhubbackup'
            with zipfile.ZipFile(bad, 'w') as z:
                z.writestr('database/x.bak', b'changed')
                z.writestr('manifest.json', json.dumps({'archive_files': [
                    {'name': 'database/x.bak', 'sha256': '0' * 64}]}))
            ok, errors = backup.verify_archive(bad)
            self.assertFalse(ok); self.assertTrue(any('hash mismatch' in x for x in errors))

    def test_selective_restore_follows_differential_parent(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); sha = hashlib.sha256(b'image-bytes').hexdigest()
            attachment = {'sha256': sha, 'storage_name': sha + '.webp', 'thumbnail_name': None}
            full = root / 'TaskHub_full_1.taskhubbackup'
            make_archive(full, {'kind': 'FULL', 'attachments': [attachment]},
                         {'database/full.bak': b'db', 'files/' + attachment['storage_name']: b'image-bytes'})
            diff = root / 'TaskHub_diff_2.taskhubbackup'
            make_archive(diff, {'kind': 'DIFFERENTIAL', 'parent_full': full.name,
                                'attachments': [attachment]}, {'database/diff.bak': b'diff'})
            old = backup.FILE_DIR; backup.FILE_DIR = str(root / 'restored')
            try:
                restored = restore_backup.selective_file_restore(diff, sha)
            finally:
                backup.FILE_DIR = old
            self.assertEqual(restored['sha256'], sha)
            self.assertEqual((root / 'restored' / attachment['storage_name']).read_bytes(), b'image-bytes')

    def test_encrypted_chat_restore_follows_differential_parent(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            cipher = b'ciphertext-only-chat-file'
            sha = hashlib.sha256(cipher).hexdigest()
            item = {
                'sha256': sha, 'storage_name': 'opaque-object.cipher',
                'conversation_id': 5, 'key_version': 2,
            }
            full = root / 'TaskHub_full_chat.taskhubbackup'
            make_archive(
                full,
                {'kind': 'FULL', 'encrypted_chat_files': [item]},
                {
                    'database/full.bak': b'db',
                    'chat_cipher/' + item['storage_name']: cipher,
                },
            )
            diff = root / 'TaskHub_diff_chat.taskhubbackup'
            make_archive(
                diff,
                {
                    'kind': 'DIFFERENTIAL', 'parent_full': full.name,
                    'encrypted_chat_files': [item],
                },
                {'database/diff.bak': b'diff'},
            )
            old = backup.CHAT_FILE_DIR
            backup.CHAT_FILE_DIR = str(root / 'restored_chat')
            try:
                restored = restore_backup.selective_chat_file_restore(diff, sha)
            finally:
                backup.CHAT_FILE_DIR = old
            self.assertEqual(restored['sha256'], sha)
            self.assertEqual(
                (root / 'restored_chat' / item['storage_name']).read_bytes(),
                cipher,
            )

    def test_server_chat_key_restore_is_atomic_and_exact(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            staging = root / 'staging'
            (staging / 'chat').mkdir(parents=True)
            expected = b'example-fernet-key-bytes-for-restore'
            (staging / 'chat' / 'server_chat_fernet.key').write_bytes(expected)
            old = backup.SERVER_CHAT_KEY_PATH
            backup.SERVER_CHAT_KEY_PATH = str(root / 'live' / 'server_chat_fernet.key')
            try:
                self.assertTrue(restore_backup.restore_server_chat_key(staging))
                self.assertEqual(pathlib.Path(backup.SERVER_CHAT_KEY_PATH).read_bytes(), expected)
                self.assertFalse(pathlib.Path(backup.SERVER_CHAT_KEY_PATH + '.restore_tmp').exists())
            finally:
                backup.SERVER_CHAT_KEY_PATH = old

    def test_extract_rejects_zip_slip(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td); archive = root / 'unsafe.taskhubbackup'
            make_archive(archive, {'kind': 'FULL', 'attachments': []},
                         {'database/x.bak': b'db', '../escape.txt': b'no'})
            with self.assertRaisesRegex(RuntimeError, 'unsafe archive member'):
                restore_backup.extract_checkpoint(archive, root / 'out')


if __name__ == '__main__':
    unittest.main(verbosity=2)
