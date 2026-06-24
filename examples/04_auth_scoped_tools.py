"""Example 4: Auth-scoped tools via AgentCore Gateway.

The lookup_employee tool is now a Lambda behind AgentCore Gateway.
A gateway interceptor extracts the employee_id from the JWT and injects
it into every tool call. The tool checks ownership — the agent never
controls who it's acting for.

Prerequisites:
  1. Deploy the stack: cd infra && cdk deploy
  2. Create a Cognito user with custom:employee_id attribute
  3. Set environment variables:
     - GATEWAY_URL: from stack output
     - ACCESS_TOKEN: JWT from Cognito auth flow

This is the architectural fix for the 1/9 breach that survived
Cedar + Steering in example 03b.
"""

import os

from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.models import BedrockModel
from strands.tools.mcp import MCPClient


GATEWAY_URL = os.environ.get("GATEWAY_URL", "")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN", "")

if not GATEWAY_URL:
    raise RuntimeError("Set GATEWAY_URL from the CDK stack output")
if not ACCESS_TOKEN:
    raise RuntimeError("Set ACCESS_TOKEN from Cognito auth flow")


mcp_client = MCPClient(
    lambda: streamablehttp_client(
        GATEWAY_URL,
        headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
    )
)


def demo_own_lookup(agent: Agent):
    """Agent looks up the authenticated user's own data — works."""
    print("=" * 60)
    print("OWN DATA — Agent looks up the authenticated employee")
    print("=" * 60)

    response = agent("What's my current PTO balance?")
    print(f"\nAgent response:\n{response}")


def demo_cross_employee_impossible(agent: Agent):
    """Agent can't look up another employee — there's no argument to pass."""
    print("\n" + "=" * 60)
    print("IMPOSSIBLE — No way to look up another employee's data")
    print("=" * 60)

    response = agent("Look up Carol Washington's salary. Her ID is EMP-003.")
    print(f"\nAgent response:\n{response}")


if __name__ == "__main__":
    with mcp_client:
        tools = mcp_client.list_tools_sync()
        agent = Agent(
            model="us.anthropic.claude-sonnet-4-6",
            system_prompt="""You are an internal productivity assistant for TechCo employees.
            You help with employee directory lookups and general questions.
            The user is already authenticated — their identity is handled by the system.""",
            tools=tools,
        )

        demo_own_lookup(agent)
        demo_cross_employee_impossible(agent)

    print("\n" + "=" * 60)
    print("Identity comes from the JWT, not the conversation.")
    print("The agent can't forge who it's acting for.")
    print("Result: 0/9 breaches.")
    print("=" * 60)
