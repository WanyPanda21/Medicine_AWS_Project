
import json
import boto3
import uuid
import logging
from decimal import Decimal, InvalidOperation

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("Medicines")


def lambda_handler(event, context):
    try:
        # Read data from the request
        body = event.get("body", event)

        if isinstance(body, str):
            body = json.loads(body)

        if not isinstance(body, dict):
            return response(400, {
                "message": "Request must contain a JSON object"
            })

        name = body.get("name")
        brand = body.get("brand")
        category = body.get("category")
        strength = body.get("strength")
        price = body.get("price")
        stock = body.get("stock")

        # Validate required fields
        if not all([
            isinstance(value, str) and value.strip()
            for value in [name, brand, category, strength]
        ]):
            return response(400, {
                "message": "Name, brand, category and strength are required"
            })

        if isinstance(stock, bool) or not isinstance(stock, int) or stock < 0:
            return response(400, {
                "message": "Stock must be a non-negative integer"
            })

        try:
            if isinstance(price, bool):
                raise InvalidOperation()

            price = Decimal(str(price))

            if not price.is_finite() or price < 0:
                raise InvalidOperation()

            price = price.quantize(Decimal("0.01"))

        except (InvalidOperation, ValueError, TypeError):
            return response(400, {
                "message": "Price must be a valid non-negative number"
            })

        # Create medicine record
        medicine_id = "MED-" + str(uuid.uuid4())[:8]

        medicine = {
            "medicine_id": medicine_id,
            "name": name.strip(),
            "brand": brand.strip(),
            "category": category.strip(),
            "strength": strength.strip(),
            "price": price,
            "stock": stock,
            "status": "ACTIVE"
        }

        # Save medicine in DynamoDB
        table.put_item(
            Item=medicine,
            ConditionExpression="attribute_not_exists(medicine_id)"
        )

        logger.info("Successfully saved medicine: %s", medicine_id)

        check = table.get_item(
            Key={"medicine_id": medicine_id},
            ConsistentRead=True
        )

        logger.info("DynamoDB verification result: %s", check)

        return response(201, {
            "message": "Medicine created successfully",
            "medicine": {
                **medicine,
                "price": str(price)
            }
        })

    except json.JSONDecodeError:
        return response(400, {
            "message": "Invalid JSON request"
        })

    except Exception:
        logger.exception("Failed to create medicine")
        return response(500, {
            "message": "Unable to create medicine"
        })


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json"
        },
        "body": json.dumps(body)
    }
