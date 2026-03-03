"""
One-time setup script — creates the 'dealiq' MySQL database.

Run once before starting the app:
    python create_db.py

Uses pymysql (sync) so it works before the async app is running.
The app itself uses aiomysql for async SQLAlchemy.
"""
import os
import sys
import pymysql
from dotenv import load_dotenv

load_dotenv()

# Parse host/password from DATABASE_URL if set, otherwise use defaults
DATABASE_URL = os.getenv("DATABASE_URL", "")
host = "localhost"
port = 3306
password = ""
user = "root"

if DATABASE_URL:
    # mysql+aiomysql://user:password@host:port/dbname
    try:
        without_scheme = DATABASE_URL.split("://", 1)[1]           # user:pass@host:port/db
        userinfo, hostinfo = without_scheme.rsplit("@", 1)
        user, password = (userinfo.split(":", 1) + [""])[:2]
        host_port, _ = hostinfo.split("/", 1)
        if ":" in host_port:
            host, port_str = host_port.split(":", 1)
            port = int(port_str)
        else:
            host = host_port
    except Exception:
        pass  # fall back to defaults above

print(f"Connecting to MySQL at {host}:{port} as '{user}'...")

try:
    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
    )
    cursor = conn.cursor()
    cursor.execute(
        "CREATE DATABASE IF NOT EXISTS dealiq "
        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
    )
    conn.commit()
    print("[OK] Database 'dealiq' created (or already exists)")
    conn.close()
except pymysql.err.OperationalError as e:
    print(f"[FAIL] Could not connect to MySQL: {e}")
    print()
    print("Troubleshooting:")
    print("  1. Is MySQL running?  Open MySQL Workbench and check the connection.")
    print("  2. Is the password correct?  Check DATABASE_URL in backend/.env")
    print("  3. No password set?  Use: mysql+aiomysql://root:@localhost:3306/dealiq")
    sys.exit(1)
