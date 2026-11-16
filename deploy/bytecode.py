"""Adds bytecode to the package for AWS Lambda (TASKS.md 14.2a), called by zappa once it has written the zip
(`callbacks` in zappa_settings.json): a Lambda cannot write bytecode, so without it every new instance compiles every
module it loads.

Compiled from the sources in the zip, so also those of the Linux builds zappa swaps in for packages with compiled
parts (falcon, cryptography, …), which the deploy virtualenv does not hold. Hash-based and unchecked (PEP 552): zappa
writes the zip without file times, so bytecode checked by time would count as outdated; and nothing changes a source
on Lambda, so the import need not read it to compare.
"""

import importlib.util
import marshal
import sys
import warnings
import zipfile
from typing import Any

LAMBDA_ROOT = '/var/task/'  # where Lambda unpacks the zip: the path a traceback shows
UNCHECKED_HASH = (1).to_bytes(4, 'little')


def bytecode(source: bytes, path: str) -> bytes | None:
    """The content of the .pyc file of this source; none if it does not compile (a template, code for another Python)."""
    try:
        code = compile(source, path, 'exec', dont_inherit=True)
    except (SyntaxError, ValueError):
        return None
    return importlib.util.MAGIC_NUMBER + UNCHECKED_HASH + importlib.util.source_hash(source) + marshal.dumps(code)


def add_bytecode(zip_path: str) -> int:
    """Adds the bytecode of every module in the zip, as zappa adds a file (readable by all); answers how many."""
    count = 0
    with zipfile.ZipFile(zip_path, 'a', zipfile.ZIP_DEFLATED) as package, warnings.catch_warnings():
        warnings.simplefilter('ignore')  # the packages' own SyntaxWarnings
        present = set(package.namelist())
        for name in sorted(present):
            cached = importlib.util.cache_from_source(name)
            content = bytecode(package.read(name), LAMBDA_ROOT + name) if name.endswith('.py') else None
            if content and cached not in present:
                entry = zipfile.ZipInfo(cached)
                entry.create_system, entry.external_attr = 3, 0o755 << 16
                package.writestr(entry, content, zipfile.ZIP_DEFLATED)
                count += 1
    return count


def add_to_package(zappa_cli: Any) -> None:
    """zappa's `zip` callback. Bytecode only fits the Python that wrote it, so this one must be the Lambda's."""
    python = f'python{sys.version_info.major}.{sys.version_info.minor}'
    if zappa_cli.runtime != python:
        raise SystemExit(f'Bytecode of {python} does not fit the runtime {zappa_cli.runtime}: deploy with that Python')
    print(f'Added the bytecode of {add_bytecode(zappa_cli.zip_path)} modules to {zappa_cli.zip_path}')
