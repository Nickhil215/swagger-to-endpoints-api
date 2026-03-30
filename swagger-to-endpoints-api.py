import json
import logging
import urllib.parse
from contextlib import asynccontextmanager
from typing import Any, Dict

import requests
import urllib3
from fastapi import FastAPI, HTTPException, Query, status
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Ensure logs use standard format
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Manage configuration with Pydantic BaseSettings
class Settings(BaseSettings):
    bob_url: str = (
        "https://ig.gov-cloud.ai/bob-camunda/v1.0/camunda/execute/019beb0a-7405-72f0-950a-6319eb4806cc?env=TEST&sync=false"
    )
    bob_owner_id: str = "2cf76e5f-26ad-4f2c-bccc-f4bc1e7bfb64"
    bob_agent_id: str = "485b5c86e5094a21a0b87ipp1"
    api_token: str = ""
    agent_validation_url: str = "https://ig.gov-cloud.ai/mobius-b-service/v1.0/agents"
    verify_ssl: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()

if not settings.verify_ssl:
    # DeprecationWarning for verify=False suppression
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    logger.warning("SSL verification is disabled. Do not use in production.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up Swagger to Endpoints API")
    if not settings.api_token:
        logger.warning(
            "API_TOKEN is not set in environment variables. Calls requiring it will fail."
        )
    yield
    logger.info("Shutting down Swagger to Endpoints API")


app = FastAPI(
    title="Swagger to Endpoints",
    description="Extracts API endpoints from a Swagger/OpenAPI specification URL",
    version="1.0.0",
    lifespan=lifespan,
)


# --- Models --- #


class SwaggerInput(BaseModel):
    swagger_urls: str = Field(alias="swaggerUrls")
    endpoints: str = Field(alias="endPoints")
    model_config = {"populate_by_name": True}


class SwaggerIp(BaseModel):
    swagger_ip: SwaggerInput = Field(alias="swaggerIp")
    model_config = {"populate_by_name": True}


class EndpointResponse(BaseModel):
    loa_ip: SwaggerIp = Field(alias="loaIp")
    model_config = {"populate_by_name": True}


class EncodeRequest(BaseModel):
    json_data: Dict[str, Any]


class DecodeRequest(BaseModel):
    encoded_string: str


class ExecuteRequest(BaseModel):
    swagger_url: str = Query(default="https://ig.gov-cloud.ai/ecore/v3/api-docs")


class AgentDetails(BaseModel):
    id: str
    name: str
    description: str


class ValidateAgentIdRequest(BaseModel):
    agent_id: str = Field(alias="agentId")
    name: str = "testing02833"
    description: str = "testing"
    model_config = {"populate_by_name": True}


# --- Utilities --- #


def fetch_and_parse_swagger(url: str) -> Dict[str, Any]:
    """Fetch and parse a Swagger/OpenAPI spec from the given URL."""
    try:
        response = requests.get(url, verify=settings.verify_ssl, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch Swagger spec from {url}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch Swagger spec: {e}",
        )

    try:
        data = response.json()
    except ValueError:
        logger.error("Swagger response is not valid JSON")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Response is not valid JSON",
        )

    endpoints = []
    for path, methods in data.get("paths", {}).items():
        for method in methods:
            if method.upper() in [
                "GET",
                "POST",
                "PUT",
                "DELETE",
                "PATCH",
                "HEAD",
                "OPTIONS",
            ]:
                endpoints.append(f"{method.upper()}::{path}")

    endpoints.sort()

    return {
        "loaIp": {
            "swaggerIp": {
                "swaggerUrls": url,
                "endPoints": ",".join(endpoints),
            }
        }
    }


# --- HTTP Endpoints --- #


@app.post("/encode", summary="Encode JSON to URL-encoded string")
def encode_json(request: EncodeRequest):
    """Takes a JSON object and returns its URL-encoded string representation."""
    try:
        json_string = json.dumps(request.json_data, indent=2)
        encoded = urllib.parse.quote(json_string, safe="")
        return {"encoded": encoded}
    except Exception as e:
        logger.exception("Error during JSON encoding")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Encoding failed: {e}"
        )


@app.post("/decode", summary="Decode URL-encoded string to JSON")
def decode_json(request: DecodeRequest):
    """Takes a URL-encoded string and returns the decoded JSON object."""
    try:
        decoded_string = urllib.parse.unquote(request.encoded_string)
        json_data = json.loads(decoded_string)
        return {"decoded": json_data}
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Decoded string is not valid JSON: {e}",
        )
    except Exception as e:
        logger.exception("Error during JSON decoding")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Decoding failed: {e}"
        )


@app.get(
    "/parse",
    response_model=EndpointResponse,
    response_model_by_alias=True,
    summary="Parse Swagger spec via query param",
)
def get_endpoints(
    url: str = Query(
        default="https://ig.gov-cloud.ai/ecore/v3/api-docs",
        description="URL of the Swagger/OpenAPI spec",
    ),
):
    """Fetch a Swagger/OpenAPI spec from the given URL and return extracted endpoints."""
    return fetch_and_parse_swagger(url)


@app.post("/parse-and-execute", summary="Parse, Encode, and Execute BOB API")
def parse_and_execute(request: ExecuteRequest):
    """
    Automates the flow:
    1. Parse Swagger URL to get loaIp object
    2. URL-encode the loaIp object
    3. POST to BOB Camunda execute API
    """
    loa_ip_data = fetch_and_parse_swagger(request.swagger_url)

    try:
        json_string = json.dumps(loa_ip_data, indent=2)
        encoded_loa_ip = urllib.parse.quote(json_string, safe="")
    except Exception as e:
        logger.exception("Failed to encode parsed swagger data.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Encoding failed: {e}"
        )

    payload = {
        "ownerId": settings.bob_owner_id,
        "curl": "false",
        "swagger": "true",
        "agentId": settings.bob_agent_id,
        "LOAip": encoded_loa_ip,
    }

    headers = {"Authorization": f"Bearer {settings.api_token}"}

    logger.debug(f"Executing BOB API with payload: {payload}")

    try:
        response = requests.post(
            settings.bob_url,
            headers=headers,
            data=payload,
            verify=settings.verify_ssl,
            timeout=60,
        )
        try:
            return response.json()
        except ValueError:
            return {"response": response.text, "status_code": response.status_code}
    except requests.RequestException as e:
        logger.error(f"BOB API execution failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"BOB API execution failed: {e}",
        )


@app.post("/validate-agent", summary="Validate Agent ID")
def validate_agent_id(agent: ValidateAgentIdRequest):
    """Refactored internal agent ID validation utilizing the configured authentication token."""
    payload = {
        "agentDetails": {
            "id": agent.agent_id,
            "name": agent.name,
            "description": agent.description,
        }
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.api_token}",
    }

    try:
        response = requests.post(
            settings.agent_validation_url,
            headers=headers,
            json=payload,
            verify=settings.verify_ssl,
            timeout=30,
        )
        try:
            return response.json()
        except ValueError:
            return {"response": response.text, "status_code": response.status_code}
    except requests.RequestException as e:
        logger.error(f"Agent validation call failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Validation service call failed: {e}",
        )


@app.get("/health", summary="Health check")
def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)