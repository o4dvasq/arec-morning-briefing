"""
Calls Anthropic Claude API to generate the briefing narrative.
"""

import os
import anthropic
from briefing.prompt_builder import build_prompt


def generate_briefing(events, emails, memory, config) -> str:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    system_prompt, user_prompt = build_prompt(events, emails, memory, config)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    return message.content[0].text
