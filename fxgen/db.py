"""MySQL connection from MYSQL_HOST, MYSQL_PORT, MYSQL_USER and MYSQL_PASSWORD.

Without MYSQL_PASSWORD, the password is read from Windows Credential Manager
(generic credential "fxgen-mysql"), so scheduled runs need no password in a
file. Store it once with:  cmdkey /generic:fxgen-mysql /user:root /pass
"""
from __future__ import annotations

import os
import sys

import mysql.connector

CREDENTIAL = "fxgen-mysql"


def stored_password() -> str | None:
    """The password of a generic credential in Windows Credential Manager, if any."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class CREDENTIAL_W(ctypes.Structure):
        _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                    ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
                    ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_char)),
                    ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                    ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]

    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    cred = ctypes.POINTER(CREDENTIAL_W)()
    if not advapi.CredReadW(CREDENTIAL, 1, 0, ctypes.byref(cred)):   # 1 = CRED_TYPE_GENERIC
        return None
    try:
        blob = ctypes.string_at(cred.contents.CredentialBlob, cred.contents.CredentialBlobSize)
        return blob.decode("utf-16-le")
    finally:
        advapi.CredFree(cred)


def connect():
    password = os.environ.get("MYSQL_PASSWORD") or stored_password()
    if password is None:
        sys.exit(f"Set MYSQL_PASSWORD, or store it once with: cmdkey /generic:{CREDENTIAL} /user:root /pass")
    return mysql.connector.connect(
        host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ.get("MYSQL_USER", "root"),
        password=password,
    )
