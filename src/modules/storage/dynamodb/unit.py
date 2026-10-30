"""One transaction on the table: writes wait and go out together, atomically, when it ends (SPEC 7.2).

Reads see the transaction's own writes. Up to 100 items are written all or nothing, as in SQLite; a larger change
writes atomic chunks with `flush()` and ends with the step that closes it, so repeating it completes it.
"""

import copy
from dataclasses import dataclass
from typing import Any

from botocore.exceptions import ClientError

from src.modules.storage.dynamodb.table import Item, Table, key, to_dynamo
from src.modules.storage.errors import ConflictError, TooManyChangesError

MAX_ITEMS = 100  # DynamoDB writes at most 100 items in one transaction


@dataclass
class _Write:
    item: Item | None  # None: delete
    unique: str | None = None  # put only if the item does not exist yet; else a ConflictError with this message


class Unit:
    def __init__(self, table: Table) -> None:
        self._table = table
        self._pending: dict[tuple[str, str], _Write] = {}

    def get(self, pk: str, sk: str) -> Item | None:
        if (pk, sk) in self._pending:
            return copy.deepcopy(self._pending[pk, sk].item)
        return self._table.get(pk, sk)

    def query(self, pk: str, low: str, high: str) -> list[Item]:
        """The items of a partition with a sort key from low to high (both included), in sort key order."""
        items = {item['SK']: item for item in self._table.query(pk, low, high)} | self._pending_between(pk, low, high)
        return [items[sort_key] for sort_key in sorted(items) if items[sort_key] is not None]

    def _pending_between(self, pk: str, low: str, high: str) -> dict[str, Item | None]:
        """The transaction's own writes in that range by sort key; None for a deleted item."""
        return {sort_key: copy.deepcopy(write.item) for (partition, sort_key), write in self._pending.items()
                if partition == pk and low <= sort_key <= high}

    def query_prefix(self, pk: str, prefix: str) -> list[Item]:
        """The items of a partition whose sort key starts with the prefix, e.g. `DAY#`."""
        return self.query(pk, prefix, prefix + '\U0010ffff')

    def put(self, item: Item, unique: str | None = None) -> None:
        """Write the item (insert or replace) when the transaction ends; with `unique`, only if it does not exist yet
        (otherwise the transaction fails with a ConflictError with that message)."""
        earlier = self._pending.get((item['PK'], item['SK']))
        self._pending[item['PK'], item['SK']] = _Write(copy.deepcopy(item), unique or (earlier.unique if earlier else None))

    def delete(self, pk: str, sk: str) -> None:
        self._pending[pk, sk] = _Write(None)

    def next_id(self, kind: str) -> int:
        return self._table.next_id(kind)

    def flush(self) -> None:
        """Write the pending changes now, all or nothing: at the end of the transaction, or as a chunk of a larger one."""
        writes = list(self._pending.items())
        if not writes:
            return
        if len(writes) > MAX_ITEMS:
            raise TooManyChangesError(f'This change touches {len(writes)} records; at most {MAX_ITEMS} are saved together')
        self._transact(writes)
        self._pending.clear()

    def _transact(self, writes: list[tuple[tuple[str, str], _Write]]) -> None:
        try:
            self._table.transact([_operation(self._table.name, pk, sk, write) for (pk, sk), write in writes])
        except ClientError as error:
            conflict = _conflict(error, [write for _, write in writes])
            if conflict is None:
                raise
            raise conflict from error


def _operation(table: str, pk: str, sk: str, write: _Write) -> dict[str, Any]:
    if write.item is None:
        return {'Delete': {'TableName': table, 'Key': key(pk, sk)}}
    put: dict[str, Any] = {'TableName': table, 'Item': to_dynamo(write.item)}
    if write.unique:
        put['ConditionExpression'] = 'attribute_not_exists(PK)'
    return {'Put': put}


def _conflict(error: ClientError, writes: list[_Write]) -> ConflictError | None:
    """A failed condition or a concurrent change as ConflictError; None for other errors."""
    if error.response['Error']['Code'] != 'TransactionCanceledException':
        return None
    reasons = [reason.get('Code') for reason in error.response.get('CancellationReasons', [])]
    for write, reason in zip(writes, reasons):
        if reason == 'ConditionalCheckFailed':
            return ConflictError(write.unique)
    return ConflictError('Changed at the same time by another request; please try again')
