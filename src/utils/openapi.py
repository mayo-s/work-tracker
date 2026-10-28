"""Write the OpenAPI spec for the generated TypeScript types: python -m src.utils.openapi [--check].

The spec file is committed; `npm run api-types` turns it into src/templates/ts/api-types.ts.
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from src.app import create_app
from src.modules.pages.resources import TEMPLATES_DIR
from src.modules.storage.database import Database
from src.utils.spec import spec

SPEC_FILE = TEMPLATES_DIR / 'openapi.json'


def openapi_document() -> dict[str, Any]:
    """The spec of the app, built on a throwaway database."""
    with tempfile.TemporaryDirectory() as folder:
        create_app(Database(Path(folder) / 'spec.db'))
        return spec.spec


def render(document: dict[str, Any]) -> str:
    return json.dumps(document, indent=2, ensure_ascii=False) + '\n'


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='python -m src.utils.openapi', description=__doc__.split(':')[0] + '.')
    parser.add_argument('--check', action='store_true', help='only check that the spec file is up to date')
    args = parser.parse_args(argv)
    current = render(openapi_document())
    if args.check:
        up_to_date = SPEC_FILE.is_file() and SPEC_FILE.read_text(encoding='utf-8') == current
        print(f'{SPEC_FILE} is up to date' if up_to_date else f'{SPEC_FILE} is outdated: run python -m src.utils.openapi')
        return 0 if up_to_date else 1
    SPEC_FILE.write_text(current, encoding='utf-8')
    print(f'Wrote {SPEC_FILE}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
