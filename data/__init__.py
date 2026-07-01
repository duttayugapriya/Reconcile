# data/__init__.py
from pathlib import Path
from .generate import generate, write_db, DB_PATH

# Ensure the database is generated automatically if it's missing when imported.
if not DB_PATH.exists():
    write_db(generate())
