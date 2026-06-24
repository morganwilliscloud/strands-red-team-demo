"""
Gateway Interceptor — extracts the authenticated employee_id from the JWT
in the Authorization header and injects it into every tool call's arguments.

The agent never controls identity. It comes from the session.
"""
import base64
import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event, context):
    logger.info("Interceptor event: %s", json.dumps(event, default=str))

    mcp = event.get("mcp", {})
    gw_request = mcp.get("gatewayRequest", {})
    headers = gw_request.get("headers", {})
    body = gw_request.get("body", {})

    method = body.get("method", "")
    params = body.get("params", {})

    if method != "tools/call":
        return {
            "interceptorOutputVersion": "1.0",
            "mcp": {
                "transformedGatewayRequest": {
                    "body": body,
                },
            },
        }

    authenticated_employee_id = ""
    auth_header = headers.get("Authorization", "") or headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            token = auth_header[7:]
            payload = token.split(".")[1] + "=="
            claims = json.loads(base64.b64decode(payload))
            authenticated_employee_id = claims.get("custom:employee_id", "")
        except Exception as e:
            logger.warning("JWT decode failed: %s", e)

    if authenticated_employee_id and method == "tools/call":
        if "arguments" not in params:
            params["arguments"] = {}
        params["arguments"]["_authenticated_employee_id"] = authenticated_employee_id
        body["params"] = params
        logger.info("Injected employee_id=%s into tool call", authenticated_employee_id)

    return {
        "interceptorOutputVersion": "1.0",
        "mcp": {
            "transformedGatewayRequest": {
                "body": body,
            },
        },
    }
