import sqlite3
from pathlib import Path
import shutil
import sys

def backup_file(src: Path) -> Path:
    dst = src.with_suffix(src.suffix + ".bak")
    shutil.copy2(src, dst)
    return dst

def list_tables(conn):
    cur = conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table' ORDER BY name")
    return cur.fetchall()

def get_table_columns(conn, table_name):
    cur = conn.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cur.fetchall()]

def copy_table_data(src_conn, dst_conn, table_name):
    cols = get_table_columns(src_conn, table_name)
    if not cols:
        return 0

    col_list = ", ".join([f'"{c}"' for c in cols])
    placeholders = ", ".join(["?"] * len(cols))

    inserted = 0
    try:
        rows = src_conn.execute(f'SELECT {col_list} FROM "{table_name}"')
        for row in rows:
            try:
                dst_conn.execute(
                    f'INSERT INTO "{table_name}" ({col_list}) VALUES ({placeholders})',
                    row
                )
                inserted += 1
            except Exception:
                # یک ردیف خراب می‌تواند رد شود
                continue
    except Exception:
        pass

    return inserted

def main():
    if len(sys.argv) != 3:
        print("Usage: python recover_sqlite.py broken.db recovered.db")
        sys.exit(1)

    src_path = Path(sys.argv[1])
    dst_path = Path(sys.argv[2])

    if not src_path.exists():
        print(f"Source not found: {src_path}")
        sys.exit(1)

    backup = backup_file(src_path)
    print(f"Backup created: {backup}")

    src_conn = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    dst_conn = sqlite3.connect(dst_path)

    try:
        tables = list_tables(src_conn)
        print("Tables:", [t[0] for t in tables])

        for table_name, create_sql in tables:
            if not create_sql:
                continue
            try:
                dst_conn.execute(create_sql)
                count = copy_table_data(src_conn, dst_conn, table_name)
                print(f"{table_name}: recovered {count} rows")
            except Exception as e:
                print(f"{table_name}: skipped ({e})")

        dst_conn.commit()
        print(f"Recovery done: {dst_path}")

    finally:
        src_conn.close()
        dst_conn.close()

if __name__ == "__main__":
    main()
