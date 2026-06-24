#!/usr/bin/env python3
import aws_cdk as cdk
from stacks.gateway_stack import EmployeeLookupGatewayStack

app = cdk.App()

EmployeeLookupGatewayStack(
    app,
    "EmployeeLookupGatewayStack",
    description="Auth-scoped employee lookup tool behind AgentCore Gateway with MCP interceptor",
)

app.synth()
