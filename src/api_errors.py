# -*- coding: utf-8 -*-
"""Error text that is safe to return from the JSON API.

Database-driver and operating-system errors name servers, databases, tables,
logins and file paths. Endpoints used to return ``str(exc)`` for every failure,
so any user on the network could read those details. The full error now goes
to the log, and remote clients get a short Persian message instead. Requests
from the server machine itself (the desktop window) still see the real error,
which keeps first-time setup diagnosable.
"""
import logging
import sys

from flask import has_request_context, request

DB_ERROR_MESSAGE = 'خطای پایگاه داده رخ داد؛ جزئیات در فایل لاگ سرور ثبت شد'
SERVER_ERROR_MESSAGE = 'خطای داخلی سرور رخ داد؛ جزئیات در فایل لاگ سرور ثبت شد'

# Application code raises these with a message written for the user.
USER_FACING_ERRORS = (ValueError, PermissionError)

_LOCAL_ADDRESSES = ('127.0.0.1', '::1')


def _is_local_request():
    return has_request_context() and request.remote_addr in _LOCAL_ADDRESSES


def public_error(exc):
    """Return the message for ``exc`` that may be shown to the API client."""
    if isinstance(exc, USER_FACING_ERRORS):
        return str(exc)
    logging.getLogger('taskhub').error('API request failed: %s', exc, exc_info=exc)
    if _is_local_request():
        return str(exc)
    driver_error = getattr(sys.modules.get('pyodbc'), 'Error', None)
    if isinstance(driver_error, type) and isinstance(exc, driver_error):
        return DB_ERROR_MESSAGE
    return SERVER_ERROR_MESSAGE
