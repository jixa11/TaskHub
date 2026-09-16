# -*- coding: utf-8 -*-
"""Central configuration loader for TaskHub.
Priority in desktop builds: taskhub_config.json > environment variables > safe defaults.
Never commit production passwords to source control.
"""
import json
import os

import sys
BASE_DIR = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
# Files shipped with the application (UI, icons, fonts): <_MEIPASS>/web inside
# the EXE, src/web when running from source.
WEB_DIR = os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))), 'web')
CONFIG_PATH = os.environ.get('TASKHUB_CONFIG', os.path.join(BASE_DIR, 'taskhub_config.json'))


def _load_file():
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception as exc:
        raise RuntimeError('Invalid configuration file %s: %s' % (CONFIG_PATH, exc))


_CFG = _load_file()


def _get(name, default=None):
    # The file beside the EXE is authoritative. This prevents stale Windows
    # environment variables (for example TASKHUB_DB_TRUSTED=true) from silently
    # overriding an edited taskhub_config.json.
    if name in _CFG:
        return _CFG.get(name)
    value = os.environ.get(name)
    if value is not None and value != '':
        return value
    return default


APP_VERSION = '1.0.0'
PORT = int(_get('TASKHUB_PORT', 19234))
LAN_HTTP_ONLY = str(_get('TASKHUB_LAN_HTTP_ONLY', 'true')).lower() in ('1', 'true', 'yes', 'on')
# The LAN build must remain reachable even when an old 8.0.2 configuration
# is left beside the new EXE. In HTTP-only LAN mode, stale host/TLS/proxy
# settings are intentionally ignored.
HOST = '0.0.0.0' if LAN_HTTP_ONLY else str(_get('TASKHUB_HOST', '0.0.0.0'))
PUBLIC_HOST = str(_get('TASKHUB_PUBLIC_HOST', '') or '').strip()
SESSION_HOURS = max(1, int(_get('TASKHUB_SESSION_HOURS', 16)))
INITIAL_ADMIN_PASSWORD = str(_get('TASKHUB_INITIAL_ADMIN_PASSWORD', ''))
DB_DRIVER = str(_get('TASKHUB_DB_DRIVER', 'ODBC Driver 17 for SQL Server'))
DB_SERVER = str(_get('TASKHUB_DB_SERVER', 'localhost'))
DB_NAME = str(_get('TASKHUB_DB_NAME', 'TaskHub'))
DB_USER = str(_get('TASKHUB_DB_USER', ''))
DB_PASSWORD = str(_get('TASKHUB_DB_PASSWORD', ''))
DB_TRUSTED = str(_get('TASKHUB_DB_TRUSTED', 'true')).lower() in ('1', 'true', 'yes', 'on')
DB_ENCRYPT = str(_get('TASKHUB_DB_ENCRYPT', 'no'))
DB_TRUST_CERT = str(_get('TASKHUB_DB_TRUST_SERVER_CERTIFICATE', 'yes'))

_REQUESTED_CHAT_MODE = str(_get('TASKHUB_CHAT_MODE', 'server')).strip().lower()
if _REQUESTED_CHAT_MODE not in ('server', 'e2e'):
    raise RuntimeError('TASKHUB_CHAT_MODE must be server or e2e.')
# The zero-configuration LAN release always uses the durable server key.
# Ignoring an old e2e setting prevents browser/device keys from locking prior
# conversations after logout, login or a Windows/server restart.
CHAT_MODE = 'server' if LAN_HTTP_ONLY else _REQUESTED_CHAT_MODE
DB_MAX_CONCURRENCY = max(2, min(32, int(_get('TASKHUB_DB_MAX_CONCURRENCY', 12))))
AUTO_FIREWALL = str(_get('TASKHUB_AUTO_FIREWALL', 'true')).lower() in ('1', 'true', 'yes', 'on')
def _optional_path(name):
    raw = str(_get(name, '') or '').strip()
    if not raw:
        return ''
    return raw if os.path.isabs(raw) else os.path.join(BASE_DIR, raw)


if LAN_HTTP_ONLY:
    # Deliberately ignore certificate paths and reverse-proxy flags inherited
    # from previous releases. Waitress serves plain HTTP on the LAN address.
    SSL_CERT_FILE = ''
    SSL_KEY_FILE = ''
    SSL_ENABLED = False
    REVERSE_PROXY = False
    SERVER_ENGINE = 'waitress'
    INTERNAL_SCHEME = 'http'
    URL_SCHEME = 'http'
else:
    SSL_CERT_FILE = _optional_path('TASKHUB_SSL_CERT_FILE')
    SSL_KEY_FILE = _optional_path('TASKHUB_SSL_KEY_FILE')
    if bool(SSL_CERT_FILE) != bool(SSL_KEY_FILE):
        raise RuntimeError('Both TASKHUB_SSL_CERT_FILE and TASKHUB_SSL_KEY_FILE must be configured together.')
    if SSL_CERT_FILE and (not os.path.isfile(SSL_CERT_FILE) or not os.path.isfile(SSL_KEY_FILE)):
        raise RuntimeError('Configured HTTPS certificate or private-key file does not exist.')
    SSL_ENABLED = bool(SSL_CERT_FILE and SSL_KEY_FILE)
    REVERSE_PROXY = str(_get('TASKHUB_REVERSE_PROXY', 'false')).lower() in ('1', 'true', 'yes', 'on')
    SERVER_ENGINE = str(_get('TASKHUB_SERVER_ENGINE', 'waitress')).strip().lower()
    INTERNAL_SCHEME = 'http' if REVERSE_PROXY else ('https' if SSL_ENABLED else 'http')
    URL_SCHEME = str(_get('TASKHUB_EXTERNAL_SCHEME', 'https' if REVERSE_PROXY else INTERNAL_SCHEME)).strip().lower()
    if URL_SCHEME not in ('http', 'https'):
        raise RuntimeError('TASKHUB_EXTERNAL_SCHEME must be http or https.')
    if REVERSE_PROXY and SSL_ENABLED:
        raise RuntimeError('When TASKHUB_REVERSE_PROXY=true, terminate TLS at IIS and remove app certificate paths.')


def connection_string(database=None):
    db = database or DB_NAME
    parts = [
        'DRIVER={%s}' % DB_DRIVER,
        'SERVER=%s' % DB_SERVER,
        'DATABASE=%s' % db,
    ]
    if DB_TRUSTED:
        parts.append('Trusted_Connection=yes')
    else:
        if not DB_USER or not DB_PASSWORD:
            raise RuntimeError('Database credentials are missing. Set TASKHUB_DB_USER and TASKHUB_DB_PASSWORD.')
        parts.extend(['UID=%s' % DB_USER, 'PWD=%s' % DB_PASSWORD])
    parts.extend([
        'Encrypt=%s' % DB_ENCRYPT,
        'TrustServerCertificate=%s' % DB_TRUST_CERT,
        'Connection Timeout=15',
    ])
    return ';'.join(parts) + ';'
