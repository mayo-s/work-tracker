"""Create the DynamoDB table once: python -m src.modules.storage.dynamodb create-table NAME [--region eu-central-1].

It uses the local AWS credentials (e.g. AWS_PROFILE); the app on Lambda then finds the table by $WORK_TRACKER_TABLE.
"""

import argparse

import boto3

from src.modules.storage.dynamodb.table import REGION, TTL_ATTRIBUTE, create_table


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog='python -m src.modules.storage.dynamodb', description=__doc__.split(':')[0] + '.')
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('create-table', help='create the table and wait until it is ready')
    create.add_argument('name', help='table name, e.g. work-tracker')
    create.add_argument('--region', default=REGION, help=f'AWS region (default: {REGION})')
    args = parser.parse_args(argv)
    create_table(boto3.client('dynamodb', region_name=args.region), args.name)
    print(f'Created {args.name} in {args.region}: on-demand, time to live on {TTL_ATTRIBUTE}, point-in-time recovery on, '
          'protected against deletion')


if __name__ == '__main__':
    main()
