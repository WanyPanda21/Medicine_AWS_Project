import json
import boto3
import uuid
from decimal import Decimal


# Connect to DynamoDB
dynamodb = boto3.resource("dynamodb")

# Get our DynamoDB table
table = dynamodb.Table("Medicines")


def lambda_handler(event, context):

    medicine_id = "MED-" + str(uuid.uuid4())[:8]

    medicine = {
        "medicine_id": medicine_id,
        "name": "ABC Fever Tablet",
        "brand": "ABC Pharma",
        "category": "Fever",
        "strength": "500mg",
        "price": Decimal("120.00"),
        "stock": 100,
        "status": "ACTIVE"
    }

    # Save medicine in DynamoDB
    table.put_item(Item=medicine)

    return {
        "statusCode": 201,
        "body": json.dumps({
            "message": "Medicine created successfully",
            "medicine_id": medicine_id
        })
    }