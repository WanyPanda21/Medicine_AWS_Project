
import logging
import os
import uuid
from decimal import Decimal, InvalidOperation
from pathlib import Path
import json
from botocore.exceptions import ClientError, BotoCoreError

import boto3
from botocore.exceptions import ClientError
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from mangum import Mangum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent

AWS_REGION = os.getenv("AWS_REGION", "ap-southeast-2")

CREATE_LAMBDA = os.getenv(
    "CREATE_MEDICINE_FUNCTION", "create_medicine"
)

GET_LAMBDA = os.getenv(
    "GET_MEDICINES_FUNCTION", "get_medicines"
)

lambda_client = boto3.client(
    "lambda",
    region_name=AWS_REGION,
)

app = FastAPI(title="Medicine Management API", version="1.0.0")
app.mount(
    "/static",
    StaticFiles(directory=str(BASE_DIR / "static")),
    name="static",
)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def invoke_backend_lambda(
    function_name: str,
    payload: dict,
) -> dict:
    response = lambda_client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode("utf-8"),
    )

    result = json.loads(response["Payload"].read())

    if response.get("FunctionError"):
        logger.error(
            "Lambda %s failed: %s",
            function_name,
            result,
        )
        raise RuntimeError(
            f"Backend Lambda {function_name} failed"
        )

    # Handle the API Gateway-style response.
    if isinstance(result, dict) and "statusCode" in result:
        status_code = result["statusCode"]
        body = result.get("body", {})

        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                body = {"message": body}

        if status_code >= 400:
            raise RuntimeError(
                body.get("message", "Backend Lambda request failed")
                if isinstance(body, dict)
                else "Backend Lambda request failed"
            )

        return body if isinstance(body, dict) else {"data": body}

    return result


def validate_medicine(data: dict) -> dict:
    required_fields = ("name", "brand", "category", "strength")

    for field in required_fields:
        value = data.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field.capitalize()} is required")

    stock = data.get("stock")
    if isinstance(stock, bool) or not isinstance(stock, int) or stock < 0:
        raise ValueError("Stock must be a non-negative integer")

    try:
        raw_price = data.get("price")
        if isinstance(raw_price, bool) or raw_price is None:
            raise InvalidOperation()

        price = Decimal(str(raw_price))
        if not price.is_finite() or price < 0:
            raise InvalidOperation()

        price = price.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Price must be a valid non-negative number")

    return {
        "medicine_id": "MED-" + str(uuid.uuid4())[:8],
        "name": data["name"].strip(),
        "brand": data["brand"].strip(),
        "category": data["category"].strip(),
        "strength": data["strength"].strip(),
        "price": price,
        "stock": stock,
        "status": "ACTIVE",
    }


def create_medicine_record(data: dict) -> dict:
    # Keep your existing FastAPI validation.
    medicine = validate_medicine(data)

    # Send the data to AWS Lambda, not DynamoDB.
    payload = {
        "name": medicine["name"],
        "brand": medicine["brand"],
        "category": medicine["category"],
        "strength": medicine["strength"],
        "price": format(medicine["price"], ".2f"),
        "stock": medicine["stock"],
    }

    result = invoke_backend_lambda(
        CREATE_LAMBDA,
        payload,
    )

    # Your create Lambda returns:
    # {"message": "...", "medicine": {...}}
    created_medicine = result.get("medicine")

    if not isinstance(created_medicine, dict):
        raise RuntimeError(
            "Create Lambda returned an invalid response"
        )

    logger.info(
        "Created medicine through AWS Lambda: %s",
        created_medicine.get("medicine_id"),
    )

    return created_medicine

def get_all_medicines() -> list:
    result = invoke_backend_lambda(
        GET_LAMBDA,
        {},
    )

    # Expected response:
    # {"medicines": [...]}
    medicines = result.get("medicines")

    if not isinstance(medicines, list):
        raise RuntimeError(
            "Get Medicines Lambda returned an invalid response"
        )

    for medicine in medicines:
        if "price" in medicine:
            medicine["price"] = format(
                Decimal(str(medicine["price"])),
                ".2f",
            )

    return medicines


@app.get("/", response_class=HTMLResponse)
def home(request: Request, message: str | None = None):
    try:
        medicines = get_all_medicines()
        error = None
    except Exception:
        logger.exception("Failed to load medicines")
        medicines = []
        error = "Unable to load medicines. Please try again."

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "medicines": medicines,
            "message": message,
            "error": error,
        },
    )


@app.get("/admin", response_class=HTMLResponse)
def admin(request: Request, error: str | None = None):
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"error": error},
    )


@app.post("/admin/medicines", response_class=HTMLResponse)
def create_from_form(
    request: Request,
    name: str = Form(...),
    brand: str = Form(...),
    category: str = Form(...),
    strength: str = Form(...),
    price: str = Form(...),
    stock: str = Form(...),
):
    try:
        # Parse integer stock strictly; don't accept values like 2.5.
        if not stock.strip() or not stock.strip().isdigit():
            raise ValueError("Stock must be a non-negative integer")

        medicine = create_medicine_record({
            "name": name,
            "brand": brand,
            "category": category,
            "strength": strength,
            "price": price,
            "stock": int(stock),
        })

        return RedirectResponse(
            url="/?message=Medicine+created+successfully",
            status_code=303,
        )

    except ValueError as exc:
        return templates.TemplateResponse(
            request=request,
            name="admin.html",
            context={"error": str(exc)},
            status_code=400,
        )
    except Exception:
        logger.exception("Failed to create medicine from form")
        return templates.TemplateResponse(
            request=request,
            name="admin.html",
            context={
                "error": "Unable to create medicine. Please try again."
            },
            status_code=500,
        )


@app.post("/medicines", status_code=201)
def create_medicine_api(data: dict):
    from fastapi import HTTPException

    try:
        medicine = create_medicine_record(data)
        return {
            "message": "Medicine created successfully",
            "medicine": medicine,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ClientError:
        logger.exception("DynamoDB create operation failed")
        raise HTTPException(
            status_code=500,
            detail="Unable to create medicine",
        )
    except Exception:
        logger.exception("Unexpected create error")
        raise HTTPException(
            status_code=500,
            detail="Unable to create medicine",
        )


@app.get("/medicines")
def list_medicines_api():
    try:
        return {"medicines": get_all_medicines()}
    except Exception:
        logger.exception("DynamoDB scan failed")
        from fastapi import HTTPException
        raise HTTPException(
            status_code=500,
            detail="Unable to retrieve medicines",
        )


# AWS Lambda entry point; local development uses uvicorn.
handler = Mangum(app)