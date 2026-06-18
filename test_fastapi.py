from fastapi import FastAPI, Query
from fastapi.testclient import TestClient
from typing import List, Optional
import pydantic
print(pydantic.__version__)

app = FastAPI()

@app.get("/test")
def test_endpoint(assets: List[str] = Query(..., min_length=1)):
    return {"assets": assets}

client = TestClient(app)

print(client.get("/test?assets=").status_code)
print(client.get("/test").status_code)
