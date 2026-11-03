
import os
import json
import logging
from pathlib import Path

import boto3

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from mangum import Mangum


# --------------------------------------------------
# 1. Logging Configuration
# --------------------------------------------------

logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)


# --------------------------------------------------
# 2. Project Configuration
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

AWS_REGION = os.getenv(
    "AWS_REGION",
    "ap-southeast-2"
)

CREATE_LAMBDA = os.getenv(
    "CREATE_MEDICINE_FUNCTION",
    "create_medicine"
)

GET_LAMBDA = os.getenv(
    "GET_MEDICINES_FUNCTION",
    "get_medicines"
)


# --------------------------------------------------
# 3. AWS Lambda Client
# --------------------------------------------------

lambda_client = boto3.client(
    "lambda",
    region_name=AWS_REGION
)


# --------------------------------------------------
# 4. FastAPI Application
# --------------------------------------------------

app = FastAPI(
    title="Medicine Management API",
    description="FastAPI API layer for Medicine Management",
    version="1.0.0"
)


# --------------------------------------------------
# 5. Serve Frontend Static Files
# --------------------------------------------------

app.mount(
    "/static",
    StaticFiles(
        directory=str(BASE_DIR / "static")
    ),
    name="static"
)


# --------------------------------------------------
# 6. Frontend Pages
# --------------------------------------------------

@app.get("/", include_in_schema=False)
def home():

    return FileResponse(
        BASE_DIR / "templates" / "index.html"
    )


@app.get("/admin", include_in_schema=False)
def admin():

    return FileResponse(
        BASE_DIR / "templates" / "admin.html"
    )


# --------------------------------------------------
# 7. Common Function to Invoke Backend Lambda
# --------------------------------------------------

def invoke_backend_lambda(
    function_name: str,
    payload: dict
):

    try:

        logger.info(
            "Invoking backend Lambda: %s",
            function_name
        )

        response = lambda_client.invoke(

            FunctionName=function_name,

            InvocationType="RequestResponse",

            Payload=json.dumps(payload).encode("utf-8")

        )


        # Read Lambda response

        result = json.loads(
            response["Payload"].read()
        )


        # Check Lambda execution error

        if response.get("FunctionError"):

            logger.error(
                "Lambda execution failed: %s",
                result
            )

            raise HTTPException(
                status_code=502,
                detail="Backend Lambda execution failed"
            )


        # Handle API Gateway-style Lambda response

        if isinstance(result, dict) and "statusCode" in result:

            status_code = result["statusCode"]

            body = result.get("body", {})


            if isinstance(body, str):

                try:

                    body = json.loads(body)

                except json.JSONDecodeError:

                    body = {
                        "message": body
                    }


            if status_code >= 400:

                raise HTTPException(
                    status_code=status_code,
                    detail=body
                )


            return body


        # Return normal Lambda response

        return result


    except HTTPException:

        raise


    except Exception:

        logger.exception(
            "Error invoking backend Lambda: %s",
            function_name
        )

        raise HTTPException(
            status_code=502,
            detail="Unable to communicate with backend Lambda"
        )


# --------------------------------------------------
# 8. GET API - Fetch All Medicines
# --------------------------------------------------

@app.get("/api/medicines")
def get_medicines():

    logger.info(
        "GET API triggered - Fetching medicines"
    )


    result = invoke_backend_lambda(

        function_name=GET_LAMBDA,

        payload={}

    )


    logger.info(
        "Medicine records fetched successfully"
    )


    return result


# --------------------------------------------------
# 9. POST API - Create Medicine
# --------------------------------------------------

@app.post("/api/medicines")
async def create_medicine(request: Request):

    logger.info(
        "POST API triggered - Creating medicine"
    )


    # Read incoming JSON data from frontend

    try:

        payload = await request.json()

    except Exception:

        raise HTTPException(
            status_code=400,
            detail="Invalid JSON request"
        )


    # Validate request body type

    if not isinstance(payload, dict):

        raise HTTPException(
            status_code=400,
            detail="Request body must be a JSON object"
        )


    # Forward payload to Create Medicine Lambda

    result = invoke_backend_lambda(

        function_name=CREATE_LAMBDA,

        payload=payload

    )


    logger.info(
        "Medicine created successfully through backend Lambda"
    )


    return result


# --------------------------------------------------
# 10. AWS Lambda Handler
# --------------------------------------------------

handler = Mangum(app)
