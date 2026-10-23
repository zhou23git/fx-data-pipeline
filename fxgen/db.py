"""MySQL connection from MYSQL_HOST, MYSQL_PORT, MYSQL_USER and MYSQL_PASSWORD."""
from __future__ import annotations

import os
import sys

import mysql.connector


def connect():
    password = os.environ.get("MYSQL_PASSWORD")
    if password is None:
        sys.exit("Set MYSQL_PASSWORD (and MYSQL_HOST/PORT/USER if not 127.0.0.1:3306 root).")
    return mysql.connector.connect(
        host=os.environ.get("MYSQL_HOST", "127.0.0.1"),
        port=int(os.environ.get("MYSQL_PORT", "3306")),
        user=os.environ.get("MYSQL_USER", "root"),
        password=password,
    )
