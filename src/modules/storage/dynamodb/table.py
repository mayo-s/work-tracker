"""The one DynamoDB table (SPEC 7.2): keys `PK` / `SK`, on-demand capacity, time to live, point-in-time recovery.

Items are plain dicts here, converted from and to DynamoDB's typed format; whole numbers come back as int, others as
Decimal.
"""

from decimal import Decimal
from typing import Any

from boto3.dynamodb.types import TypeDeserializer, TypeSerializer

from src.modules.storage.dynamodb.keys import COUNTER

REGION = 'eu-central-1'  # Frankfurt
TTL_ATTRIBUTE = 'expires_at'  # epoch seconds: DynamoDB deletes the item some time after (e.g. sessions)

Item = dict[str, Any]
_serializer, _deserializer = TypeSerializer(), TypeDeserializer()


def to_dynamo(item: Item) -> dict[str, Any]:
    return {name: _serializer.serialize(value) for name, value in item.items()}


def from_dynamo(item: dict[str, Any]) -> Item:
    return {name: _plain(_deserializer.deserialize(value)) for name, value in item.items()}


def _plain(value: Any) -> Any:
    """Whole numbers as int (DynamoDB returns every number as Decimal), also within lists and maps."""
    if isinstance(value, list):
        return [_plain(element) for element in value]
    if isinstance(value, dict):
        return {name: _plain(element) for name, element in value.items()}
    return _number(value)


def _number(value: Any) -> Any:
    return int(value) if isinstance(value, Decimal) and value == value.to_integral_value() else value


def attributes(item: Item) -> Item:
    """The item without its keys, e.g. as the fields of a model."""
    return {name: value for name, value in item.items() if name not in ('PK', 'SK')}


def key(pk: str, sk: str) -> dict[str, Any]:
    return to_dynamo({'PK': pk, 'SK': sk})


class Table:
    """Reads (strongly consistent), atomic writes and id counters on one table."""

    def __init__(self, client: Any, name: str) -> None:
        self.client = client
        self.name = name

    def get(self, pk: str, sk: str) -> Item | None:
        response = self.client.get_item(TableName=self.name, Key=key(pk, sk), ConsistentRead=True)
        return from_dynamo(response['Item']) if 'Item' in response else None

    def query(self, pk: str, low: str, high: str) -> list[Item]:
        """The items of a partition with a sort key from low to high (both included), in sort key order; all pages."""
        request = {
            'TableName': self.name, 'ConsistentRead': True, 'KeyConditionExpression': 'PK = :pk AND SK BETWEEN :low AND :high',
            'ExpressionAttributeValues': to_dynamo({':pk': pk, ':low': low, ':high': high}),
        }
        items = []
        while True:
            response = self.client.query(**request)
            items += [from_dynamo(item) for item in response['Items']]
            if 'LastEvaluatedKey' not in response:
                return items
            request['ExclusiveStartKey'] = response['LastEvaluatedKey']

    def transact(self, operations: list[dict[str, Any]]) -> None:
        """Write all or nothing (at most 100 operations, each on another item)."""
        self.client.transact_write_items(TransactItems=operations)

    def next_id(self, kind: str) -> int:
        """A new id for a kind of record: 1, 2, …, never given twice (an atomic counter, outside any transaction)."""
        response = self.client.update_item(
            TableName=self.name, Key=key(COUNTER, kind), UpdateExpression='ADD #value :one',
            ExpressionAttributeNames={'#value': 'value'}, ExpressionAttributeValues=to_dynamo({':one': 1}),
            ReturnValues='UPDATED_NEW',
        )
        return int(_deserializer.deserialize(response['Attributes']['value']))


def create_table(client: Any, name: str) -> None:
    """Create the table and wait until it is ready: on-demand, time to live on `expires_at`, point-in-time recovery
    (restores to any second of the last 35 days), and protected against deletion."""
    client.create_table(
        TableName=name, BillingMode='PAY_PER_REQUEST', DeletionProtectionEnabled=True,
        KeySchema=[{'AttributeName': 'PK', 'KeyType': 'HASH'}, {'AttributeName': 'SK', 'KeyType': 'RANGE'}],
        AttributeDefinitions=[{'AttributeName': 'PK', 'AttributeType': 'S'}, {'AttributeName': 'SK', 'AttributeType': 'S'}],
    )
    client.get_waiter('table_exists').wait(TableName=name)
    client.update_time_to_live(TableName=name, TimeToLiveSpecification={'Enabled': True, 'AttributeName': TTL_ATTRIBUTE})
    client.update_continuous_backups(
        TableName=name, PointInTimeRecoverySpecification={'PointInTimeRecoveryEnabled': True})
