"""Import a yearly spreadsheet export: python -m src.modules.importer SHEET.csv [--replace] [--db PATH]."""

import argparse
import sys

from src.modules.importer.run import import_file
from src.modules.storage.database import Database, database_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m src.modules.importer', description=__doc__.split(':')[0] + '.')
    parser.add_argument('sheet', help='CSV export of one year (Date, Start, End, Pause, Sum, Comment)')
    parser.add_argument('--replace', action='store_true', help="replace the year's days and entries if it was imported before")
    parser.add_argument('--db', default=database_path(), help='database file (default: $WORK_TRACKER_DB or work_tracker.db)')
    args = parser.parse_args(argv)
    try:
        summary, reconciliation = import_file(Database(args.db), args.sheet, args.replace)
    except (OSError, ValueError, LookupError) as error:
        print(f'Import failed, nothing was written: {error}', file=sys.stderr)
        return 1
    print('\n'.join([*summary.lines(), '', *reconciliation.lines()]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
