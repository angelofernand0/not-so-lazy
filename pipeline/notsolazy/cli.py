"""Offline setup commands. Unimplemented stages are deliberately not exposed."""

import argparse
import json

from sqlalchemy.engine import make_url

from notsolazy import __version__
from notsolazy.config import Settings
from notsolazy.models import Base, make_engine


def main() -> None:
    parser = argparse.ArgumentParser(prog="nsl", description="Not So Lazy filing pipeline")
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="Report configuration without exposing secrets")
    doctor.add_argument("--require-sec", action="store_true", help="Validate contact for EDGAR")
    commands.add_parser("init-db", help="Check database access and initialize registered tables")
    args = parser.parse_args()
    try:
        settings = Settings()
        if args.command == "doctor":
            if args.require_sec:
                settings.require_sec_identity()
            print(
                json.dumps(
                    {
                        "version": __version__,
                        "database_backend": make_url(
                            settings.database_url.get_secret_value()
                        ).get_backend_name(),
                        "blob_backend": settings.blob_backend,
                        "section_item": settings.section_item,
                        "sec_identity_configured": bool(settings.sec_user_agent.strip()),
                        "summaries_enabled": settings.summaries_enabled,
                        "milestone": 1,
                    },
                    indent=2,
                )
            )
        elif args.command == "init-db":
            url = make_url(settings.database_url.get_secret_value())
            if url.get_backend_name() == "sqlite" and url.database and url.database != ":memory:":
                from pathlib import Path

                Path(url.database).parent.mkdir(parents=True, exist_ok=True)
            engine = make_engine(settings.database_url.get_secret_value())
            try:
                Base.metadata.create_all(engine)
                with engine.connect():
                    pass
            finally:
                engine.dispose()
            print("Database reachable. No stage tables are registered in the scaffold yet.")
    except ValueError:
        parser.exit(2, "Configuration invalid. Check .env and SEC_USER_AGENT for EDGAR commands.\n")


if __name__ == "__main__":
    main()
