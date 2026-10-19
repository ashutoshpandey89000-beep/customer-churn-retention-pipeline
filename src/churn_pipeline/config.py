"""Database configuration and connection utilities."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def is_running_in_docker():
    """Detect whether current process is executing inside a Docker container."""
    return Path("/.dockerenv").exists() or os.getenv("RUNNING_IN_DOCKER") == "true"


def database_url(host=None, port=None, user=None, password=None, db=None):
    """Construct PostgreSQL SQLAlchemy connection URL.

    Auto-detects host vs containerized environment:
    - If running inside a container: resolves 'postgres' on port 5432.
    - If running on host (outside docker): automatically routes 'postgres' to 'localhost'
      on port 5433 (to avoid port collisions with any local PostgreSQL instance on 5432).
    """
    if os.getenv("DATABASE_URL") and not any([host, port, user, password, db]):
        return os.getenv("DATABASE_URL")

    in_docker = is_running_in_docker()
    env_host = os.getenv("POSTGRES_HOST")

    if host:
        db_host = host
    elif not in_docker and (env_host == "postgres" or not env_host):
        db_host = "localhost"
    else:
        db_host = env_host or "localhost"

    db_user = user or os.getenv("POSTGRES_USER", "churn_user")
    db_pass = password or os.getenv("POSTGRES_PASSWORD", "change_me_local_only")
    db_name = db or os.getenv("POSTGRES_DB", "churn_analytics")

    if port:
        db_port = str(port)
    elif not in_docker and db_host in ("localhost", "127.0.0.1"):
        db_port = os.getenv("POSTGRES_EXTERNAL_PORT", "5433")
    else:
        db_port = os.getenv("POSTGRES_PORT", "5432")

    return f"postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
