import argparse
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import database


def create_backup(destination=None):
    source_path = database.DATABASE_PATH
    if not source_path.is_file():
        raise FileNotFoundError(f"Database not found: {source_path}")
    if destination is None:
        directory = source_path.parent / "backups"
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = directory / f"venito-{stamp}.sqlite3"
    else:
        destination = Path(destination).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.resolve() == source_path.resolve():
        raise ValueError("Backup destination must differ from the live database.")

    source = sqlite3.connect(source_path)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    os.chmod(destination, 0o600)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Create a consistent SQLite backup of VENTO.")
    parser.add_argument("destination", nargs="?", help="Optional backup file path")
    args = parser.parse_args()
    print(create_backup(args.destination))
