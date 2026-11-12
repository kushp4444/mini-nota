"""Apply idempotent run schema migration with the schema-owner connection.

Runtime RUN_DATABASE_URL may use the narrower run-writer grants documented in
migrations/README.md. No catalog rows or frozen model assets are modified.
"""
import argparse
import os
from service.run_repository import RunRepository


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database-url', default=os.environ.get('RUN_DATABASE_URL'))
    args = parser.parse_args()
    if not args.database_url:
        parser.error('Set RUN_DATABASE_URL or --database-url')
    RunRepository(args.database_url).initialize()


if __name__ == '__main__':
    main()
