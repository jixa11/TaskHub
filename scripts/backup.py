# -*- coding: utf-8 -*-
"""Verified, chain-safe backup for TaskHub v8.

Each checkpoint contains the SQL Server backup, ordinary attachment files and
end-to-end encrypted chat files that belong to that checkpoint, a JSON
manifest and SHA-256 hashes.  The database connection configuration itself is
never written to the archive.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import sys
import tempfile
import zipfile

try:
    import pyodbc
except ImportError:
    print('pyodbc is not installed. Run: pip install pyodbc')
    sys.exit(1)

# Application modules live in ../src.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'src'))
from config import APP_VERSION, BASE_DIR, DB_NAME, connection_string


CONN_STR = connection_string()
BACKUP_DIR = os.path.abspath(os.environ.get('TASKHUB_BACKUP_DIR', os.path.join(BASE_DIR, 'backups')))
# SQL Server itself writes the .bak file.  When SQL Server is on another
# machine this must be a shared/UNC directory visible with the same path to
# both the SQL Server service account and this application process.
SQL_BACKUP_DIR = os.path.abspath(os.environ.get('TASKHUB_SQL_BACKUP_DIR', BACKUP_DIR))
FILE_DIR = os.path.join(BASE_DIR, 'data', 'files')
CHAT_FILE_DIR = os.path.join(BASE_DIR, 'taskhub_data', 'chat_cipher')
SERVER_CHAT_KEY_PATH = os.path.join(BASE_DIR, 'taskhub_data', 'server_chat_fernet.key')
LOCK_PATH = os.path.join(BASE_DIR, 'data', 'backup.lock')
FULL_BACKUP_WEEKDAY = int(os.environ.get('TASKHUB_FULL_BACKUP_WEEKDAY', '5'))
RETENTION_DAYS = max(7, int(os.environ.get('TASKHUB_BACKUP_RETENTION_DAYS', '30')))


def _log(message):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    line = '[%s] %s' % (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), message)
    print(line)
    try:
        with open(os.path.join(BACKUP_DIR, 'backup.log'), 'a', encoding='utf-8') as stream:
            stream.write(line + '\n')
    except Exception:
        pass


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def _archives():
    if not os.path.isdir(BACKUP_DIR):
        return []
    return sorted([os.path.join(BACKUP_DIR, x) for x in os.listdir(BACKUP_DIR)
                   if x.lower().endswith('.taskhubbackup')])


def _latest_full_manifest():
    for path in reversed(_archives()):
        if '_full_' not in os.path.basename(path).lower():
            continue
        try:
            with zipfile.ZipFile(path) as archive:
                return json.loads(archive.read('manifest.json').decode('utf-8'))
        except Exception:
            continue
    return None


def _attachment_manifest(conn):
    """Read only metadata for active attachments from the live database."""
    result = []
    cur = conn.cursor()
    try:
        # Archived attachment links are intentionally included as well; soft
        # delete must remain recoverable from a later FULL checkpoint.
        cur.execute("""SELECT DISTINCT b.sha256,b.storage_name,b.thumbnail_name,b.size_bytes,b.mime_type
            FROM FileBlobs b JOIN Attachments a ON a.blob_id=b.id ORDER BY b.sha256""")
    except Exception:
        return result
    for row in cur.fetchall():
        result.append({'sha256': row[0], 'storage_name': row[1], 'thumbnail_name': row[2],
                       'size_bytes': int(row[3] or 0), 'mime_type': row[4]})
    return result


def _chat_file_manifest(conn):
    """Read encrypted-chat file metadata without ever accessing plaintext.

    Archived rows are included deliberately so a FULL checkpoint remains a
    complete recovery point.  The server stores ciphertext only.
    """
    result = []
    cur = conn.cursor()
    try:
        cur.execute("""SELECT id,conversation_id,storage_name,ciphertext_sha256,
                size_bytes,key_version,is_active
            FROM ChatEncryptedFiles ORDER BY ciphertext_sha256,id""")
    except Exception:
        return result
    for row in cur.fetchall():
        result.append({
            'id': int(row[0]), 'conversation_id': int(row[1]),
            'storage_name': row[2], 'sha256': row[3],
            'size_bytes': int(row[4] or 0), 'key_version': int(row[5] or 1),
            'is_active': bool(row[6]),
        })
    return result


def _run_sql_backup(kind, path):
    options = 'DIFFERENTIAL, INIT' if kind == 'DIFFERENTIAL' else 'INIT'
    sql = ("BACKUP DATABASE [%s] TO DISK=N'%s' WITH %s, COMPRESSION, CHECKSUM, NAME=N'%s-%s', STATS=10"
           % (DB_NAME, path.replace("'", "''"), options, DB_NAME, kind.title()))
    try:
        conn = pyodbc.connect(CONN_STR, autocommit=True, timeout=30)
        cur = conn.cursor(); cur.execute(sql)
        while cur.nextset():
            pass
        # RESTORE VERIFYONLY validates SQL Server's own backup checksums.
        cur.execute("RESTORE VERIFYONLY FROM DISK=N'%s' WITH CHECKSUM" % path.replace("'", "''"))
        while cur.nextset():
            pass
        conn.close()
        return
    except Exception as exc:
        if 'COMPRESSION' not in str(exc).upper():
            raise
    # SQL Server editions without compression support still get checksums.
    conn = pyodbc.connect(CONN_STR, autocommit=True, timeout=30)
    cur = conn.cursor(); cur.execute(sql.replace(', COMPRESSION', ''))
    while cur.nextset():
        pass
    cur.execute("RESTORE VERIFYONLY FROM DISK=N'%s' WITH CHECKSUM" % path.replace("'", "''"))
    while cur.nextset():
        pass
    conn.close()


def _write_lock():
    os.makedirs(os.path.dirname(LOCK_PATH), exist_ok=True)
    with open(LOCK_PATH, 'w', encoding='utf-8') as stream:
        json.dump({'started_at': datetime.datetime.now().isoformat(), 'pid': os.getpid()}, stream)


def _clear_lock():
    try:
        os.remove(LOCK_PATH)
    except FileNotFoundError:
        pass


def verify_archive(path):
    """Verify archive structure and every recorded SHA-256 hash."""
    errors = []
    try:
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read('manifest.json').decode('utf-8'))
            for item in manifest.get('archive_files', []):
                name, expected = item['name'], item['sha256']
                try:
                    digest = hashlib.sha256(archive.read(name)).hexdigest()
                    if digest != expected:
                        errors.append('hash mismatch: ' + name)
                except KeyError:
                    errors.append('missing: ' + name)
            if 'connection_string' in json.dumps(manifest).lower() or 'password=' in json.dumps(manifest).lower():
                errors.append('configuration secret marker detected')
    except Exception as exc:
        errors.append(str(exc))
    return not errors, errors


def _cleanup_chain_safe():
    """Delete only complete old FULL+DIFF chains, never an isolated parent."""
    archives = _archives()
    chains = []
    current = []
    for path in archives:
        if '_full_' in os.path.basename(path).lower():
            if current:
                chains.append(current)
            current = [path]
        elif current:
            current.append(path)
    if current:
        chains.append(current)
    cutoff = datetime.datetime.now() - datetime.timedelta(days=RETENTION_DAYS)
    # Always retain the newest full chain, even if the machine was off longer
    # than the retention window.
    for chain in chains[:-1]:
        newest = max(datetime.datetime.fromtimestamp(os.path.getmtime(x)) for x in chain)
        if newest < cutoff:
            for path in chain:
                try:
                    os.remove(path); _log('removed old chain member: ' + os.path.basename(path))
                except Exception as exc:
                    _log('cleanup failed for %s: %s' % (path, exc))


def run_backup(force_full=False):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    os.makedirs(SQL_BACKUP_DIR, exist_ok=True)
    now = datetime.datetime.now(); stamp = now.strftime('%Y%m%d_%H%M%S')
    full_manifest = _latest_full_manifest()
    want_full = force_full or now.weekday() == FULL_BACKUP_WEEKDAY or not full_manifest
    kind = 'FULL' if want_full else 'DIFFERENTIAL'; suffix = 'full' if want_full else 'diff'
    work = tempfile.mkdtemp(prefix='taskhub_backup_')
    bak_name = '%s_%s_%s.bak' % (DB_NAME, suffix, stamp)
    bak_path = os.path.join(SQL_BACKUP_DIR, bak_name)  # SQL Server service must see this path.
    archive_path = os.path.join(BACKUP_DIR, '%s_%s_%s.taskhubbackup' % (DB_NAME, suffix, stamp))
    _write_lock()
    try:
        _log('starting %s database backup' % kind)
        _run_sql_backup(kind, bak_path)
        conn = pyodbc.connect(CONN_STR, timeout=30)
        attachments = _attachment_manifest(conn)
        encrypted_chat_files = _chat_file_manifest(conn)
        conn.close()
        previous = set()
        previous_chat = set()
        if not want_full and full_manifest:
            previous = {x.get('sha256') for x in full_manifest.get('attachments', [])}
            previous_chat = {
                x.get('sha256') for x in full_manifest.get('encrypted_chat_files', [])
            }
        selected = attachments if want_full else [x for x in attachments if x.get('sha256') not in previous]
        selected_chat = (encrypted_chat_files if want_full else [
            x for x in encrypted_chat_files if x.get('sha256') not in previous_chat
        ])
        manifest = {
            'format': 2, 'app': 'TaskHub', 'app_version': APP_VERSION,
            'database': DB_NAME, 'kind': kind, 'created_at': now.isoformat(),
            'parent_full': None if want_full else full_manifest.get('archive_name'),
            'attachments': attachments, 'included_attachment_hashes': [x['sha256'] for x in selected],
            'encrypted_chat_files': encrypted_chat_files,
            'included_chat_hashes': [x['sha256'] for x in selected_chat],
            'server_chat_key_included': os.path.isfile(SERVER_CHAT_KEY_PATH),
            'archive_name': os.path.basename(archive_path), 'archive_files': []
        }
        with zipfile.ZipFile(archive_path + '.tmp', 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.write(bak_path, 'database/' + bak_name)
            manifest['archive_files'].append({'name': 'database/' + bak_name, 'sha256': _sha256(bak_path)})
            for item in selected:
                src = os.path.join(FILE_DIR, item['storage_name'])
                if not os.path.isfile(src):
                    raise RuntimeError(
                        'referenced attachment is missing: ' + item['storage_name']
                    )
                name = 'files/' + item['storage_name']; archive.write(src, name)
                manifest['archive_files'].append({'name': name, 'sha256': _sha256(src)})
                thumb = item.get('thumbnail_name')
                tsrc = os.path.join(FILE_DIR, 'thumbs', thumb or '')
                if thumb:
                    if not os.path.isfile(tsrc):
                        raise RuntimeError(
                            'referenced thumbnail is missing: ' + thumb
                        )
                    name = 'files/thumbs/' + thumb; archive.write(tsrc, name)
                    manifest['archive_files'].append({'name': name, 'sha256': _sha256(tsrc)})
            for item in selected_chat:
                src = os.path.join(CHAT_FILE_DIR, os.path.basename(item['storage_name']))
                if not os.path.isfile(src):
                    raise RuntimeError(
                        'referenced encrypted chat file is missing: '
                        + os.path.basename(item['storage_name'])
                    )
                name = 'chat_cipher/' + os.path.basename(item['storage_name'])
                archive.write(src, name)
                manifest['archive_files'].append({
                    'name': name, 'sha256': _sha256(src)
                })
            # Server-managed LAN chat can only be recovered together with its
            # Fernet key.  The key is small, so include it in every checkpoint
            # (FULL and DIFFERENTIAL) and protect it with the archive hashes.
            if os.path.isfile(SERVER_CHAT_KEY_PATH):
                key_name = 'chat/server_chat_fernet.key'
                archive.write(SERVER_CHAT_KEY_PATH, key_name)
                manifest['archive_files'].append({
                    'name': key_name, 'sha256': _sha256(SERVER_CHAT_KEY_PATH)
                })
            archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        os.replace(archive_path + '.tmp', archive_path)
        ok, errors = verify_archive(archive_path)
        if not ok:
            raise RuntimeError('archive verification failed: ' + '; '.join(errors))
        try:
            os.remove(bak_path)
        except Exception:
            pass
        _cleanup_chain_safe()
        _log('verified checkpoint created: ' + os.path.basename(archive_path))
        return archive_path
    except Exception as exc:
        _log('backup failed: ' + str(exc))
        for path in (archive_path + '.tmp', archive_path):
            try:
                os.remove(path)
            except Exception:
                pass
        return None
    finally:
        _clear_lock()
        shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    force = '--full' in sys.argv
    result = run_backup(force_full=force)
    sys.exit(0 if result else 1)
