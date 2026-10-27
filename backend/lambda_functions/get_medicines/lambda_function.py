import os
import json
import boto3
from decimal import Decimal
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(
    os.environ.get("MEDICINE_TABLE", "MedicineTable")
)


def decimal_default(value):
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError("Type not serializable")


def lambda_handler(event, context):
    try:
        result = table.scan()                       #retrieves medicines from DynamoDB.

        medicines = result.get("Items", [])

        while "LastEvaluatedKey" in result:
            result = table.scan(
                ExclusiveStartKey=result["LastEvaluatedKey"]
            )
            medicines.extend(result.get("Items", []))

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps(
                {"medicines": medicines},
                default=decimal_default
            )
        }

    except Exception:
        logger.exception("Failed to retrieve medicines")

        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps({
                "message": "Unable to retrieve medicines"
            })
        }
