from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
import requests
import urllib3
import urllib.parse
import json

# Suppress InsecureRequestWarning for verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = FastAPI(
    title="Swagger to Endpoints",
    description="Extracts API endpoints from a Swagger/OpenAPI specification URL",
    version="1.0.0",
)


class SwaggerInput(BaseModel):
    swaggerUrls: str
    endPoints: str


class SwaggerIp(BaseModel):
    swaggerIp: SwaggerInput


class EndpointResponse(BaseModel):
    loaIp: SwaggerIp


class EncodeRequest(BaseModel):
    json_data: dict


class DecodeRequest(BaseModel):
    encoded_string: str


class ExecuteRequest(BaseModel):
    swagger_url: str = "https://ig.gov-cloud.ai/ecore/v3/api-docs"
    owner_id: str = "2cf76e5f-26ad-4f2c-bccc-f4bc1e7bfb64"
    agent_id: str = "485b5c86e5094a21a0b87ipp1"
    token: str
    bob_url: str = "https://ig.gov-cloud.ai/bob-camunda/v1.0/camunda/execute/019beb0a-7405-72f0-950a-6319eb4806cc?env=TEST&sync=false"


class ValidateAgentIdRequest(BaseModel):
    agentId: str
    name: str = "testing02833"
    description: str = "testing"



def parse_swagger(url: str) -> dict:
    """Fetch and parse a Swagger/OpenAPI spec from the given URL."""
    try:
        response = requests.get(url, verify=False, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch Swagger spec: {e}")

    try:
        data = response.json()
    except ValueError:
        raise HTTPException(status_code=422, detail="Response is not valid JSON")

    server_url = data.get("servers", [{}])[0].get("url", "")

    endpoints = []
    for path, methods in data.get("paths", {}).items():
        for method in methods:
            if method.upper() in ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]:
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


@app.post("/encode", summary="Encode JSON to URL-encoded string")
def encode_json(request: EncodeRequest):
    """Takes a JSON object and returns its URL-encoded string representation."""
    try:
        json_string = json.dumps(request.json_data, indent=2)
        encoded = urllib.parse.quote(json_string, safe='')
        return {"encoded": encoded}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Encoding failed: {e}")


@app.post("/decode", summary="Decode URL-encoded string to JSON")
def decode_json(request: DecodeRequest):
    """Takes a URL-encoded string and returns the decoded JSON object."""
    try:
        decoded_string = urllib.parse.unquote(request.encoded_string)
        json_data = json.loads(decoded_string)
        return {"decoded": json_data}
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=422, detail=f"Decoded string is not valid JSON: {e}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Decoding failed: {e}")


@app.get("/parse", response_model=EndpointResponse, summary="Parse Swagger spec via query param")
def get_endpoints(
    url: str = Query(
        default="https://ig.gov-cloud.ai/ecore/v3/api-docs",
        description="URL of the Swagger/OpenAPI spec",
    ),
):
    """Fetch a Swagger/OpenAPI spec from the given URL and return extracted endpoints."""
    return parse_swagger(url)



class ValidateAgentIdRequest(BaseModel):

    agentId: str
    name: str
    description: str
    
    



def validate_agentId(agent: ValidateAgentIdRequest):

   payload = {"agentDetails": {
        "id": agent.agentId,
        "name": agent.name,
        "description": agent.description
    }}





    


@app.post("/parse-and-execute", summary="Parse, Encode, and Execute BOB API")
def parse_and_execute(request: ExecuteRequest):
    """
    Automates the flow:
    1. Parse Swagger URL to get loaIp object
    2. URL-encode the loaIp object
    3. POST to BOB Camunda execute API
    """
    # 1. Parse
    loa_ip_data = parse_swagger(request.swagger_url)

    # 2. Encode
    try:
        json_string = json.dumps(loa_ip_data, indent=2)
        encoded_loa_ip = urllib.parse.quote(json_string, safe='')
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Encoding failed: {e}")
    # validate agentId:
    # validate_agent_id(request.agent_id)
    # 3. Execute
    payload = {
        'ownerId': request.owner_id,
        'curl': 'false',
        'swagger': 'true',
        'agentId': request.agent_id,
        'LOAip': encoded_loa_ip
    }
    headers = {
        'Authorization': f'Bearer {request.token}'
    }

    print("============================")
    print("headers", headers)
    print("payload", payload)
    print("============================")

    try:
        response = requests.post(
            request.bob_url,
            headers=headers,
            data=payload,
            verify=False,
            timeout=60
        )
        # Attempt to return JSON if possible, else text
        try:
            return response.json()
        except ValueError:
            return {"response": response.text, "status_code": response.status_code}
        # print("DONE")
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"BOB API execution failed: {e}")


@app.post("/validate-agent", summary="Validate Agent ID")
def validate_agent_id(agent: ValidateAgentIdRequest):
    """
    Validates an agent ID by calling an external service.
    """
    url = "https://ig.gov-cloud.ai/mobius-b-service/v1.0/agents"
    payload = json.dumps({
        "agentDetails": {
            "id": agent.agentId,
            "name": agent.name,
            "description": agent.description
        }
    })
    headers = {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICI3Ny1NUVdFRTNHZE5adGlsWU5IYmpsa2dVSkpaWUJWVmN1UmFZdHl5ejFjIn0.eyJleHAiOjE3NjM0ODEzNTEsImlhdCI6MTc2MzQ0NTM1MSwianRpIjoiNWNlZjA2N2UtYWQ5Yi00ZDJkLTllYWYtOGY4YmIwMTcxOTM2IiwiaXNzIjoiaHR0cDovL2tleWNsb2FrLXNlcnZpY2Uua2V5Y2xvYWsuc3ZjLmNsdXN0ZXIubG9jYWw6ODA4MC9yZWFsbXMvbWFzdGVyIiwiYXVkIjpbIkJPTFRaTUFOTl9CT1RfbW9iaXVzIiwiUEFTQ0FMX0lOVEVMTElHRU5DRV9tb2JpdXMiLCJNT05FVF9tb2JpdXMiLCJWSU5DSV9tb2JpdXMiLCJhY2NvdW50Il0sInN1YiI6IjJjZjc2ZTVmLTI2YWQtNGYyYy1iY2NjLWY0YmMxZTdiZmI2NCIsInR5cCI6IkJlYXJlciIsImF6cCI6IkhPTEFDUkFDWV9tb2JpdXMiLCJzaWQiOiJlYWZhMzQwZC0yOWIzLTQxMmItOGE4Ni0wY2Y4ZTIwNTViMDAiLCJhY3IiOiIxIiwiYWxsb3dlZC1vcmlnaW5zIjpbIi8qIl0sInJlYWxtX2FjY2VzcyI6eyJyb2xlcyI6WyI2N2UxNDcxNTA2ZGE3NTJiNzg3MTZkMjFfc3JlX2FkbWluIiwiNjdlMTQ3MTUwNmRhNzUyYjc4NzE2ZDIxX2JyX2FkbWluIiwiNjdlMTQ3MTUwNmRhNzUyYjc4NzE2ZDIxX3NlY3VyaXR5X2FkbWluIiwiMWY3OTM4ZGItY2ZlZi00OGQ1LTgwMjUtaXAxX1NVUEVSQURNSU4iLCI2N2UxNDcxNTA2ZGE3NTJiNzg3MTZkMjFfZGNkcl9hZG1pbiIsIjY3ZTE0NzE1MDZkYTc1MmI3ODcxNmQyMV9jZF9leGVjdXRlIiwiNjdlMTQ3MTUwNmRhNzUyYjc4NzE2ZDIxX2lhY19leGVjdXRlIiwidW1hX2F1dGhvcml6YXRpb24iLCJjYmJiNjU4NC0wODYxLTQwYWQtODFhNC1pcDFfU1VQRVJBRE1JTiIsIjY3ZTE0NzE1MDZkYTc1MmI3ODcxNmQyMV9kY2RyX2V4ZWN1dGUiLCI2N2UxNDcxNTA2ZGE3NTJiNzg3MTZkMjFfYnJfcmVhZCIsIjY3ZTE0NzE1MDZkYTc1MmI3ODcxNmQyMV9rOHNfcmVhZCIsIjY3ZTE0NzE1MDZkYTc1MmI3ODcxNmQyMV9DdXN0b21lcl9Xcml0ZSIsIjNhNzk5ZWRkLTRiYWEtNDNiYS1hYzVmLWlwMV9TVVBFUkFETUlOIiwiNjdlMTQ3MTUwNmRhNzUyYjc4NzE2ZDIxX2NpX3dyaXRlIiwiYWE1Y2YxNTItNjc3NC00NWRkLWJmODEtaXAxX1NVUEVSQURNSU4iLCI4NzBhNmNiNy0yYTYyLTQ1NjktYTg2YS1pcDFfU1VQRVJBRE1JTiIsIjY3ZTE0NzE1MDZkYTc1MmI3ODcxNmQyMV9zcmVfd3JpdGUiLCIwYmM0OWZhZC05MTIzLTRjYWItYWI5YS0wNTU2Nzk2MDBkMjhfYzFhNzU2NjctYjM1ZC00NmNhLWJkNGEtZDk1NGY1YmIyY2Y5X3Rlc3Ricl9yZWFkIiwiNjdlMTQ3MTUwNmRhNzUyYjc4NzE2ZDIxX2RjZHJfcmVhZCIsImM4YTBlMDgxLWZlMmItNDYyYy1iNjU1LWlwMV9TVVBFUkFETUlOIiwiNmRjOGE1NmUtOTJhYi00YzVlLWI4MzctaXAxX1NVUEVSQURNSU4iLCI2N2UxNDcxNTA2ZGE3NTJiNzg3MTZkMjFfQXBwcm92YWxzX1dyaXRlIiwiOGU3OTVhMzUtZjI5MS00NDEwLTk1NGUtaXAxX1NVUEVSQURNSU4iLCI2N2UxNDcxNTA2ZGE3NTJiNzg3MTZkMjFfUm9sZXNfUmVhZCIsIjY3ZTE0NzE1MDZkYTc1MmI3ODcxNmQyMV9BbGVydHNfV3JpdGUiLCI2N2UxNDcxNTA2ZGE3NTJiNzg3MTZkMjFfazhzX3dyaXRlIiwiZGE2NTUxNGItNGI3ZS00Y2NiLWE4MjEtaXAxX1NVUEVSQURNSU4iLCI2N2UxNDcxNTA2ZGE3NTJiNzg3MTZkMjFfaWFjX2FkbWluIiwiNjdlMTQ3MTUwNmRhNzUyYjc4NzE2ZDIxX1BvbGljaWVzX1JlYWQiLCI2N2UxNDcxNTA2ZGE3NTJiNzg3MTZkMjFfY2RfYWRtaW4iLCI2N2UxNDcxNTA2ZGE3NTJiNzg3MTZkMjFfY2lfcmVhZCIsIjY3ZTE0NzE1MDZkYTc1MmI3ODcxNmQyMV9JbmZyYV9Xcml0ZSIsIjY3ZTE0NzE1MDZkYTc1MmI3ODcxNmQyMV9Sb2xlc19Xcml0ZSIsIjY3ZTE0NzE1MDZkYTc1MmI3ODcxNmQyMV9zcmVfZXhlY3V0ZSIsIjM2OGU4ZDdmLTc5MWYtNGRiOS1iNmMzLWlwMV9TVVBFUkFETUlOIiwiNjdlMTQ3MTUwNmRhNzUyYjc4NzE2ZDIxX0luZnJhX1JlYWQiLCJiMDI3OTczOC04N2M2LTRmZDAtOWJkZi1pcDFfU1VQRVJBRE1JTiIsImEyYjE0MzAwLWMwOTEtNGY1OC1iYWFlLWlwMV9TVVBFUkFETUlOIiwiNjdlMTQ3MTUwNmRhNzUyYjc4NzE2ZDIxX2RjZHJfd3JpdGUiLCJhNDYwNjJkOS1lMmIwLTQ1YTYtYWU5MC1pcDFfU1VQRVJBRE1JTiIsIjY3ZTE0NzE1MDZkYTc1MmI3ODcxNmQyMV9Mb2dzX1JlYWQiLCI2N2UxNDcxNTA2ZGE3NTJiNzg3MTZkMjFfaWFjX3JlYWQiLCI2N2UxNDcxNTA2ZGE3NTJiNzg3MTZkMjFfazhzX2V4ZWN1dGUiLCI2N2UxNDcxNTA2ZGE3NTJiNzg3MTZkMjFfVGVhbV9Xcml0ZSIsIjY3ZTE0NzE1MDZkYTc1MmI3ODcxNmQyMV9zZWN1cml0eV9leGVjdXRlIiwiZmRjNGQzZjQtNzJhMi00MDkxLThhMTgtaXAxX1NVUEVSQURNSU4iLCI2Y2IwMTEwMS1mNmYzLTQ0YmYtYTAxYS1pcDFfU1VQRVJBRE1JTiIsIjY3ZTE0NzE1MDZkYTc1MmI3ODcxNmQyMV9jZF9yZWFkIiwib2ZmbGluZV9hY2Nlc3MiLCI2N2UxNDcxNTA2ZGE3NTJiNzg3MTZkMjFfUG9saWNpZXNfV3JpdGUiLCI2N2UxNDcxNTA2ZGE3NTJiNzg3MTZkMjFfc2VjdXJpdHlfd3JpdGUiLCIzMGRiY2JjMC05MTk0LTQ4YTEtYjJmYi1pcDFfU1VQRVJBRE1JTiIsIjY3ZTE0NzE1MDZkYTc1MmI3ODcxNmQyMV9Qcm9qZWN0X1dyaXRlIiwiZmM5YTk5NzYtNzIxNS00MWM3LWFiOWQtaXAxX1NVUEVSQURNSU4iLCJtb2JpdXNfZDBmNTJiMGUtMzZkNy00ODUzLTg4NjAtNmQyMWE5YTkyMGE1X0FCQ0QiLCJkZWZhdWx0LXJvbGVzLW1hc3RlciIsIjY3ZTE0NzE1MDZkYTc1MmI3ODcxNmQyMV9DdXN0b21lcl9SZWFkIiwiZTMyNDM0NTYtNzE5ZC00YWUwLWJjNTItaXAxX1NVUEVSQURNSU4iLCI2N2UxNDcxNTA2ZGE3NTJiNzg3MTZkMjFfVGVhbV9SZWFkIiwiNWIwOWFkMzctMWI1ZS00MzE3LWE4ZTktaXAxX1NVUEVSQURNSU4iLCI2N2UxNDcxNTA2ZGE3NTJiNzg3MTZkMjFfYnJfZXhlY3V0ZSIsIjY3ZTE0NzE1MDZkYTc1MmI3ODcxNmQyMV9rOHNfYWRtaW4iLCJlYmQ3NDc2ZS1mOGU2LTRkNGYtODM3NS1pcDFfU1VQRVJBRE1JTiIsIjY3ZTE0NzE1MDZkYTc1MmI3ODcxNmQyMV9Qcm9qZWN0X1JlYWQiLCI2N2UxNDcxNTA2ZGE3NTJiNzg3MTZkMjFfTG9nc19Xcml0ZSIsIjU0ZWVlODgwLTQxYTEtNDQ4My05NzFkLWlwMV9TVVBFUkFETUlOIiwiNjdlMTQ3MTUwNmRhNzUyYjc4NzE2ZDIxX2NkX3dyaXRlIiwiNjdlMTQ3MTUwNmRhNzUyYjc4NzE2ZDIxX2JyX3dyaXRlIiwiNjdlMTQ3MTUwNmRhNzUyYjc4NzE2ZDIxX3NyZV9yZWFkIiwiNjdlMTQ3MTUwNmRhNzUyYjc4NzE2ZDIxX1VzZXJfV3JpdGUiLCI2N2UxNDcxNTA2ZGE3NTJiNzg3MTZkMjFfaWFjX3dyaXRlIiwiNjdlMTQ3MTUwNmRhNzUyYjc4NzE2ZDIxX2NpX2FkbWluIiwiNjdlMTQ3MTUwNmRhNzUyYjc4NzE2ZDIxX3NlY3VyaXR5X3JlYWQiLCI2N2UxNDcxNTA2ZGE3NTJiNzg3MTZkMjFfY2lfZXhlY3V0ZSIsIjY3ZTE0NzE1MDZkYTc1MmI3ODcxNmQyMV9BcHByb3ZhbHNfUmVhZCIsIjY3ZTE0NzE1MDZkYTc1MmI3ODcxNmQyMV9Vc2VyX1JlYWQiXX0sInJlc291cmNlX2FjY2VzcyI6eyJCT0xUWk1BTk5fQk9UX21vYml1cyI6eyJyb2xlcyI6WyJCT0xUWk1BTk5fQk9UX1VTRVIiLCJCT0xUWk1BTk5fQk9UX0FETUlOIl19LCJIT0xBQ1JBQ1lfbW9iaXVzIjp7InJvbGVzIjpbIlNVUEVSQURNSU4iLCJIT0xBQ1JBQ1lfVVNFUiJdfSwiUEFTQ0FMX0lOVEVMTElHRU5DRV9tb2JpdXMiOnsicm9sZXMiOlsiUEFTQ0FMX0lOVEVMTElHRU5DRV9DT05TVU1FUiIsIlBBU0NBTF9JTlRFTExJR0VOQ0VfVVNFUiIsIlBBU0NBTF9JTlRFTExJR0VOQ0VfQURNSU4iLCJTQ0hFTUFfUkVBRCJdfSwiTU9ORVRfbW9iaXVzIjp7InJvbGVzIjpbIk1PTkVUX0FQUFJPVkUiLCJNT05FVF9VU0VSIl19LCJWSU5DSV9tb2JpdXMiOnsicm9sZXMiOlsiVklOQ0lfVVNFUiJdfSwiYWNjb3VudCI6eyJyb2xlcyI6WyJtYW5hZ2UtYWNjb3VudCIsIm1hbmFnZS1hY2NvdW50LWxpbmtzIiwidmlldy1wcm9maWxlIl19fSwic2NvcGUiOiJwcm9maWxlIGVtYWlsIiwicmVxdWVzdGVyVHlwZSI6IlRFTkFOVCIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJuYW1lIjoiQWlkdGFhcyBBaWR0YWFzIiwidGVuYW50SWQiOiIyY2Y3NmU1Zi0yNmFkLTRmMmMtYmNjYy1mNGJjMWU3YmZiNjQiLCJwbGF0Zm9ybUlkIjoibW9iaXVzIiwicHJlZmVycmVkX3VzZXJuYW1lIjoicGFzc3dvcmRfdGVuYW50X2FpZHRhYXNAZ2FpYW5zb2x1dGlvbnMuY29tIiwiZ2l2ZW5fbmFtZSI6IkFpZHRhYXMiLCJmYW1pbHlfbmFtZSI6IkFpZHRhYXMiLCJlbWFpbCI6InBhc3N3b3JkX3RlbmFudF9haWR0YWFzQGdhaWFuc29sdXRpb25zLmNvbSIsInBsYXRmb3JtcyI6eyJyb2xlcyI6WyJTQ0hFTUFfUkVBRCJdfX0.A8g8-Key_UXky1vxoj54Kq2--HfuHgpmvokRJSqDVr770ZKaVkuYvqdqJAVJxhXGq0Ec6Adosi8vNpiuyR_38m0me3t2u41fmb8OCyUM-xHUI3abvnNYRhMebR77rq5THjq5xTVjav2YtjGF6ypUmdKxkgnzIsreBBF-sZSjsve4Q-lUFucv21E267iokXZV5gonHSeZFC0CPnKhLyEGwmcSXqBqG_LK7SLamDlsvl7kWv0zsOcre-UzskBuN4EH6J3-78iXPg0NpHBksl23aiZYTfYapflYRYsJmxvcg47Ta5EFNu5kzEUdxBYJl-nEogMlLaNweIE0AtPQ-m0iXQ'
    }

    try:
        response = requests.post(url, headers=headers, data=payload, verify=False, timeout=30)
        try:
            return response.json()
        except ValueError:
            return {"response": response.text, "status_code": response.status_code}
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Validation service call failed: {e}")


@app.get("/health", summary="Health check")

def health():
    return {"status": "healthy"}




if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
