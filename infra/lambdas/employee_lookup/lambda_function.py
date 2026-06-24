"""
Employee Lookup Tool — returns the authenticated employee's data.

Identity comes from _authenticated_employee_id injected by the gateway
interceptor. The agent never passes an employee_id argument. The tool
uses the injected identity directly as the lookup key.
"""
import json
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

EMPLOYEE_DATA = {
    "EMP-001": {
        "name": "Alice Chen",
        "role": "Senior Engineer",
        "department": "Platform",
        "salary": "185000",
        "email": "alice.chen@techco.com",
        "manager": "EMP-003",
        "pto_balance": "18 days",
        "performance_rating": "Exceeds Expectations",
    },
    "EMP-002": {
        "name": "Bob Martinez",
        "role": "Product Manager",
        "department": "Growth",
        "salary": "170000",
        "email": "bob.martinez@techco.com",
        "manager": "EMP-003",
        "pto_balance": "12 days",
        "performance_rating": "Meets Expectations",
    },
    "EMP-003": {
        "name": "Carol Washington",
        "role": "Engineering Director",
        "department": "Platform",
        "salary": "240000",
        "email": "carol.washington@techco.com",
        "manager": "EMP-005",
        "pto_balance": "22 days",
        "performance_rating": "Exceeds Expectations",
    },
    "EMP-004": {
        "name": "David Kim",
        "role": "Junior Engineer",
        "department": "Platform",
        "salary": "120000",
        "email": "david.kim@techco.com",
        "manager": "EMP-001",
        "pto_balance": "8 days",
        "performance_rating": "Meets Expectations",
    },
}


def lambda_handler(event, context):
    logger.info("Event: %s", json.dumps(event, default=str))

    authenticated_employee_id = event.get("_authenticated_employee_id", "")

    if not authenticated_employee_id:
        return {
            "statusCode": 401,
            "body": json.dumps({"message": "No authenticated identity."}),
        }

    record = EMPLOYEE_DATA.get(authenticated_employee_id)
    if not record:
        return {
            "statusCode": 404,
            "body": json.dumps({"found": False, "message": f"No employee found with ID: {authenticated_employee_id}"}),
        }

    return {
        "statusCode": 200,
        "body": json.dumps({"found": True, "employee": record}),
    }
