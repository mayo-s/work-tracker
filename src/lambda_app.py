"""The WSGI app on AWS Lambda (`app_function` in zappa_settings.json): the stage detects Lambda, the storage is the
DynamoDB table $WORK_TRACKER_TABLE, and creating root needs the setup token.

zappa loads this module while the instance starts, not inside its first request (INSTANTIATE_LAMBDA_HANDLER_ON_IMPORT
in zappa_settings.json): what a first request would wait for is loaded here as well (TASKS.md 14.2b)."""

import datetime as dt

from src.app import create_app
from src.lib.public_holidays import holiday_on

app = create_app()
holiday_on(dt.date.today())  # the holiday calendar: its package loads ~280 modules on first use
