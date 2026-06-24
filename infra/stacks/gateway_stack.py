"""
AgentCore Gateway stack for the employee lookup tool.

Deploys:
- Cognito User Pool (with custom:employee_id attribute)
- Employee Lookup Lambda (auth-scoped tool)
- Gateway Interceptor Lambda (JWT → employee_id injection)
- AgentCore Gateway (CUSTOM_JWT auth, interceptor, MCP target)

The agent connects to the Gateway URL and gets tools via MCP.
Identity flows from Cognito JWT → interceptor → tool arguments.
"""
import os

from aws_cdk import (
    CfnOutput, Duration, Fn, RemovalPolicy, Stack,
    aws_bedrockagentcore as bac,
    aws_cognito as cognito,
    aws_iam as iam,
    aws_lambda as lambda_,
)
from constructs import Construct


class EmployeeLookupGatewayStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        _lambdas = os.path.join(os.path.dirname(__file__), "..", "lambdas")
        _cognito_issuer = f"https://cognito-idp.{self.region}.amazonaws.com"

        # ── Cognito ───────────────────────────────────────────────────────────

        self.user_pool = cognito.UserPool(self, "UserPool",
            user_pool_name="techco-employee-service",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(username=True, email=True),
            custom_attributes={
                "employee_id": cognito.StringAttribute(mutable=False),
            },
            removal_policy=RemovalPolicy.DESTROY,
        )

        self.app_client = self.user_pool.add_client("AppClient",
            user_pool_client_name="techco-employee-app",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(user_password=True, admin_user_password=True),
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[cognito.OAuthScope.OPENID, cognito.OAuthScope.PROFILE],
                callback_urls=["http://localhost:8080/callback"],
                logout_urls=["http://localhost:8080/"],
            ),
            id_token_validity=Duration.hours(1),
            access_token_validity=Duration.hours(1),
        )

        # ── Employee Lookup Lambda ────────────────────────────────────────────

        self.employee_lookup_fn = lambda_.Function(self, "EmployeeLookup",
            function_name="employee-lookup-tool",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="lambda_function.lambda_handler",
            code=lambda_.Code.from_asset(os.path.join(_lambdas, "employee_lookup")),
            timeout=Duration.seconds(30),
            memory_size=128,
        )

        # ── Gateway Interceptor Lambda ────────────────────────────────────────

        self.interceptor_fn = lambda_.Function(self, "Interceptor",
            function_name="employee-gateway-interceptor",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.lambda_handler",
            code=lambda_.Code.from_asset(os.path.join(_lambdas, "gateway_interceptor")),
            timeout=Duration.seconds(30),
            memory_size=128,
        )

        # ── AgentCore Gateway ─────────────────────────────────────────────────

        gw_role = iam.Role(self, "GatewayRole",
            role_name="EmployeeLookupGatewayRole",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
        )
        self.employee_lookup_fn.grant_invoke(gw_role)
        self.interceptor_fn.grant_invoke(gw_role)

        self.gateway = bac.CfnGateway(self, "Gateway",
            name="employee-lookup-gateway",
            protocol_type="MCP",
            role_arn=gw_role.role_arn,
            authorizer_type="CUSTOM_JWT",
            authorizer_configuration=bac.CfnGateway.AuthorizerConfigurationProperty(
                custom_jwt_authorizer=bac.CfnGateway.CustomJWTAuthorizerConfigurationProperty(
                    discovery_url=f"{_cognito_issuer}/{self.user_pool.user_pool_id}/.well-known/openid-configuration",
                    allowed_audience=[self.app_client.user_pool_client_id],
                ),
            ),
            interceptor_configurations=[
                bac.CfnGateway.GatewayInterceptorConfigurationProperty(
                    interception_points=["REQUEST"],
                    interceptor=bac.CfnGateway.InterceptorConfigurationProperty(
                        lambda_=bac.CfnGateway.LambdaInterceptorConfigurationProperty(
                            arn=self.interceptor_fn.function_arn)),
                    input_configuration=bac.CfnGateway.InterceptorInputConfigurationProperty(
                        pass_request_headers=True),
                ),
            ],
            exception_level="DEBUG",
        )

        # ── Gateway Target ────────────────────────────────────────────────────

        _cred = [bac.CfnGatewayTarget.CredentialProviderConfigurationProperty(
            credential_provider_type="GATEWAY_IAM_ROLE")]

        target = bac.CfnGatewayTarget(self, "TargetEmployeeLookup",
            name="employee-lookup-tool",
            description="Look up the current authenticated employee's information",
            gateway_identifier=self.gateway.attr_gateway_identifier,
            target_configuration=bac.CfnGatewayTarget.TargetConfigurationProperty(
                mcp=bac.CfnGatewayTarget.McpTargetConfigurationProperty(
                    lambda_=bac.CfnGatewayTarget.McpLambdaTargetConfigurationProperty(
                        lambda_arn=self.employee_lookup_fn.function_arn,
                        tool_schema=bac.CfnGatewayTarget.ToolSchemaProperty(
                            inline_payload=[
                                bac.CfnGatewayTarget.ToolDefinitionProperty(
                                    name="lookup_my_info",
                                    description="Look up the current authenticated employee's information. No arguments needed, identity is determined from the session.",
                                    input_schema=bac.CfnGatewayTarget.SchemaDefinitionProperty(
                                        type="object",
                                        properties={},
                                        required=[],
                                    ),
                                ),
                            ],
                        ),
                    ),
                ),
            ),
            credential_provider_configurations=_cred,
        )
        target.add_dependency(self.gateway)

        # ── Outputs ──────────────────────────────────────────────────────────

        CfnOutput(self, "GatewayUrl", value=self.gateway.attr_gateway_url)
        CfnOutput(self, "GatewayId", value=self.gateway.attr_gateway_identifier)
        CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id)
        CfnOutput(self, "ClientId", value=self.app_client.user_pool_client_id)
