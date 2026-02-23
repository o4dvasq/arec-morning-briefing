"""
Posts the morning briefing as a Slack DM via Slack SDK.
Setup: api.slack.com/apps → create app → OAuth scope: chat:write → install → copy bot token.
Your SLACK_USER_ID: click your name in Slack → Profile → copy Member ID (starts with U).
"""

import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError


def post_briefing(briefing_text: str) -> bool:
    client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
    user_id = os.environ["SLACK_USER_ID"]
    try:
        dm = client.conversations_open(users=[user_id])
        channel_id = dm["channel"]["id"]
        client.chat_postMessage(
            channel=channel_id,
            text=briefing_text,
            mrkdwn=True,
        )
        return True
    except SlackApiError as e:
        raise RuntimeError(f"Slack post failed: {e.response['error']}")
