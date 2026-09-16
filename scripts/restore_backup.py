# -*- coding: utf-8 -*-
"""Validate and restore TaskHub v8 checkpoint archives.

The application must be stopped before a full database restore.  A fresh full
recovery checkpoint is always created first.  Nothing happens without the
explicit confirmation phrase shown by ``--help``.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import zipfile

import pyodbc

# Application modules live in ../src.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
import backup
from config import DB_NAME, connection_string


CONFIRM_PHRASE = 'RESTORE-TASKHUB-v8'
SQL_RESTORE_DIR = os.path.abspath(os.environ.get('TASKHUB_SQL_RESTORE_DIR', backup.SQL_BACKUP_DIR))


def manifest(path):
    with zipfile.ZipFile(path) as archive:
        return json.loads(archive.read('manifest.json').decode('utf-8'))


def parent_full(diff_path, info):
    name = info.get('parent_full')
    if not name:
        raise RuntimeError('differential checkpoint has no parent_full')
    path = os.path.join(os.path.dirname(os.path.abspath(diff_path)), name)
    if not os.path.isfile(path):
        raise RuntimeError('parent FULL archive not found: ' + name)
    return path


def extract_checkpoint(path, target):
    ok, errors = backup.verify_archive(path)
    if not ok:
        raise RuntimeError('invalid checkpoint: ' + '; '.join(errors))
    with zipfile.ZipFile(path) as archive:
        # Zip-slip protection: every member must remain under target.
        root = os.path.abspath(target) + os.sep
        for item in archive.infolist():
            destination = os.path.abspath(os.path.join(target, item.filename))
            if not destination.startswith(root):
                raise RuntimeError('unsafe archive member: ' + item.filename)
        archive.extractall(target)
    info = manifest(path)
    bak_files = [os.path.join(target, x['name']) for x in info.get('archive_files', [])
                 if x['name'].startswith('database/') and x['name'].lower().endswith('.bak')]
    if len(bak_files) != 1:
        raise RuntimeError('checkpoint must contain exactly one database backup')
    return info, bak_files[0]


def copy_files(staging):
    source = os.path.join(staging, 'files')
    if not os.path.isdir(source):
        return 0
    destination = backup.FILE_DIR
    os.makedirs(destination, exist_ok=True)
    copied = 0
    for root, _, files in os.walk(source):
        rel = os.path.relpath(root, source)
        out_dir = destination if rel == '.' else os.path.join(destination, rel)
        os.makedirs(out_dir, exist_ok=True)
        for name in files:
            src, dst = os.path.join(root, name), os.path.join(out_dir, name)
            if not os.path.isfile(dst) or backup._sha256(src) != backup._sha256(dst):
                shutil.copy2(src, dst); copied += 1
    return copied


def copy_chat_files(staging):
    """Restore encrypted chat bytes from a verified checkpoint."""
    source = os.path.join(staging, 'chat_cipher')
    if not os.path.isdir(source):
        return 0
    os.makedirs(backup.CHAT_FILE_DIR, exist_ok=True)
    copied = 0
    for name in os.listdir(source):
        src = os.path.join(source, name)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(backup.CHAT_FILE_DIR, os.path.basename(name))
        if not os.path.isfile(dst) or backup._sha256(src) != backup._sha256(dst):
            shutil.copy2(src, dst)
            copied += 1
    return copied


def restore_server_chat_key(staging):
    """Restore the LAN chat master key atomically.

    Without this file, server-managed message and file ciphertext from the
    restored database cannot be opened.  The application must be stopped
    during a full restore, so replacing the key here is safe.
    """
    source = os.path.join(staging, 'chat', 'server_chat_fernet.key')
    if not os.path.isfile(source):
        return False
    os.makedirs(os.path.dirname(backup.SERVER_CHAT_KEY_PATH), exist_ok=True)
    temporary = backup.SERVER_CHAT_KEY_PATH + '.restore_tmp'
    shutil.copy2(source, temporary)
    os.replace(temporary, backup.SERVER_CHAT_KEY_PATH)
    return True


def restore_database(full_bak, diff_bak=None):
    conn = pyodbc.connect(connection_string('master'), autocommit=True, timeout=30)
    cur = conn.cursor()
    try:
        cur.execute("ALTER DATABASE [%s] SET SINGLE_USER WITH ROLLBACK IMMEDIATE" % DB_NAME)
        full_mode = 'NORECOVERY' if diff_bak else 'RECOVERY'
        cur.execute("RESTORE DATABASE [%s] FROM DISK=N'%s' WITH REPLACE,%s,CHECKSUM,STATS=10" %
                    (DB_NAME, full_bak.replace("'", "''"), full_mode))
        while cur.nextset():
            pass
        if diff_bak:
            cur.execute("RESTORE DATABASE [%s] FROM DISK=N'%s' WITH RECOVERY,CHECKSUM,STATS=10" %
                        (DB_NAME, diff_bak.replace("'", "''")))
            while cur.nextset():
                pass
    finally:
        try:
            cur.execute("ALTER DATABASE [%s] SET MULTI_USER" % DB_NAME)
        except Exception:
            pass
        conn.close()


def stage_for_sql(path, label):
    """Copy a backup to a path visible to the SQL Server service."""
    os.makedirs(SQL_RESTORE_DIR, exist_ok=True)
    target = os.path.join(SQL_RESTORE_DIR, 'taskhub_restore_%s_%s' % (label, os.path.basename(path)))
    shutil.copy2(path, target)
    return target


def selective_file_restore(path, sha):
    ok, errors = backup.verify_archive(path)
    if not ok:
        raise RuntimeError('; '.join(errors))
    info = manifest(path)
    entry = next((x for x in info.get('attachments', []) if x.get('sha256') == sha), None)
    if not entry:
        raise RuntimeError('attachment hash is not present in this checkpoint manifest')
    names = ['files/' + entry['storage_name']]
    if entry.get('thumbnail_name'):
        names.append('files/thumbs/' + entry['thumbnail_name'])
    os.makedirs(backup.FILE_DIR, exist_ok=True); os.makedirs(os.path.join(backup.FILE_DIR, 'thumbs'), exist_ok=True)
    archives = [path]
    if info.get('kind') == 'DIFFERENTIAL':
        archives.append(parent_full(path, info))
    restored = 0
    for source_path in archives:
        with zipfile.ZipFile(source_path) as archive:
            for name in names:
                try:
                    data = archive.read(name)
                except KeyError:
                    continue
                target = os.path.join(backup.FILE_DIR, name[len('files/'):])
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with open(target, 'wb') as stream:
                    stream.write(data)
                restored += 1
        if restored:
            break
    if not restored:
        raise RuntimeError('attachment bytes are missing from the selected checkpoint chain')
    return entry


def selective_chat_file_restore(path, sha):
    """Restore one encrypted chat object from a FULL/DIFF chain."""
    ok, errors = backup.verify_archive(path)
    if not ok:
        raise RuntimeError('; '.join(errors))
    info = manifest(path)
    entry = next((x for x in info.get('encrypted_chat_files', [])
                  if x.get('sha256') == sha), None)
    if not entry:
        raise RuntimeError('encrypted chat hash is not present in this checkpoint manifest')
    name = 'chat_cipher/' + os.path.basename(entry['storage_name'])
    os.makedirs(backup.CHAT_FILE_DIR, exist_ok=True)
    archives = [path]
    if info.get('kind') == 'DIFFERENTIAL':
        archives.append(parent_full(path, info))
    for source_path in archives:
        with zipfile.ZipFile(source_path) as archive:
            try:
                data = archive.read(name)
            except KeyError:
                continue
            if backup._sha256_bytes(data) != sha:
                raise RuntimeError('encrypted chat file hash mismatch')
            target = os.path.join(backup.CHAT_FILE_DIR,
                                  os.path.basename(entry['storage_name']))
            with open(target, 'wb') as stream:
                stream.write(data)
            return entry
    raise RuntimeError('encrypted chat bytes are missing from the selected checkpoint chain')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('checkpoint', help='FULL or DIFFERENTIAL .taskhubbackup archive')
    parser.add_argument('--confirm', help='required phrase: ' + CONFIRM_PHRASE)
    parser.add_argument('--attachment-sha', help='restore only one attachment; database is untouched')
    parser.add_argument('--chat-file-sha',
                        help='restore only one encrypted chat file; database is untouched')
    args = parser.parse_args()
    checkpoint = os.path.abspath(args.checkpoint)
    if not os.path.isfile(checkpoint):
        parser.error('checkpoint not found')
    if args.attachment_sha:
        item = selective_file_restore(checkpoint, args.attachment_sha)
        print('restored attachment:', item['storage_name'])
        return 0
    if args.chat_file_sha:
        item = selective_chat_file_restore(checkpoint, args.chat_file_sha)
        print('restored encrypted chat file:', item['storage_name'])
        return 0
    if args.confirm != CONFIRM_PHRASE:
        parser.error('full restore requires --confirm ' + CONFIRM_PHRASE)

    # Recovery point is mandatory.  If this fails, the destructive restore is
    # not attempted.
    recovery = backup.run_backup(force_full=True)
    if not recovery:
        raise RuntimeError('pre-restore recovery checkpoint failed; restore cancelled')
    print('pre-restore recovery checkpoint:', recovery)

    selected_info = manifest(checkpoint)
    full_archive = checkpoint
    diff_archive = None
    if selected_info.get('kind') == 'DIFFERENTIAL':
        diff_archive = checkpoint
        full_archive = parent_full(checkpoint, selected_info)
    staging_root = os.path.join(backup.BACKUP_DIR, 'restore_staging')
    if os.path.isdir(staging_root):
        shutil.rmtree(staging_root)
    os.makedirs(staging_root)
    sql_staged = []
    try:
        full_dir = os.path.join(staging_root, 'full'); os.makedirs(full_dir)
        _, full_bak = extract_checkpoint(full_archive, full_dir)
        diff_bak = None; diff_dir = None
        if diff_archive:
            diff_dir = os.path.join(staging_root, 'diff'); os.makedirs(diff_dir)
            _, diff_bak = extract_checkpoint(diff_archive, diff_dir)
        sql_full = stage_for_sql(full_bak, 'full'); sql_staged.append(sql_full)
        sql_diff = stage_for_sql(diff_bak, 'diff') if diff_bak else None
        if sql_diff: sql_staged.append(sql_diff)
        restore_database(sql_full, sql_diff)
        copied = copy_files(full_dir)
        chat_copied = copy_chat_files(full_dir)
        key_restored = restore_server_chat_key(full_dir)
        if diff_dir:
            copied += copy_files(diff_dir)
            chat_copied += copy_chat_files(diff_dir)
            # A differential checkpoint contains the current key as well.
            key_restored = restore_server_chat_key(diff_dir) or key_restored
        if selected_info.get('server_chat_key_included') and not key_restored:
            raise RuntimeError('checkpoint declares a server chat key but it was not restored')
        print('restore completed; attachment files copied:', copied,
              '; encrypted chat files copied:', chat_copied,
              '; server chat key restored:', key_restored)
    finally:
        for path in sql_staged:
            try:
                os.remove(path)
            except Exception:
                pass
        shutil.rmtree(staging_root, ignore_errors=True)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as exc:
        print('RESTORE FAILED:', exc)
        sys.exit(1)
