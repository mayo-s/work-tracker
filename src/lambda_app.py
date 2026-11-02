"""The WSGI app on AWS Lambda (`app_function` in zappa_settings.json): the stage detects Lambda, the storage is the
DynamoDB table $WORK_TRACKER_TABLE, and creating root needs the setup token."""

from src.app import create_app

app = create_app()
