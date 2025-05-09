# main.py
"""Production‑grade FastAPI service for employee search.

Features
========
* **Dataset upload** – `POST /dataset` accepts an Excel file once and returns
  a `dataset_id` (UUID). The server parses the sheet and builds an in‑memory
  FAISS index via `EmployeeSearchEngine`.
* **Query endpoint** – `POST /search` uses that `dataset_id` to retrieve a
  Top‑K shortlist (JSON) without resending the file.
* **Health check** – `GET /health` for liveness probes.

Quickstart
----------
.. code:: bash

    pip install fastapi uvicorn[standard] sentence-transformers faiss-cpu pandas tabulate python-multipart

    uvicorn main:app --reload --port 8000

1. **Upload dataset**::

       curl -F "file=@sample_employee_data_1000.xlsx" http://localhost:8000/dataset
       # → {"dataset_id": "f9a7c3b2"}

2. **Search**::

       curl -X POST http://localhost:8000/search \
            -H 'Content-Type: application/json' \
            -d '{
                  "dataset_id": "f9a7c3b2",
                  "query": "Analytics engineer for Snowflake and dbt",
                  "skills": ["snowflake", "dbt"],
                  "age_min": 30,
                  "age_max": 50,
                  "top_k": 5
                }'

Architecture notes
------------------
* A **singleton dict** (`ENGINES`) maps `dataset_id → EmployeeSearchEngine`.
* Upload route stores the Excel to a temp directory (`/tmp/...xlsx`) so the
  engine can reload on server restart if desired.
* Thread‑safe via starlette’s single‑threaded event loop; for multi‑worker
  setups behind a process manager share nothing or persist FAISS indices.

Author: <your‑name>
Date: 2025‑05‑09
"""
from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException
from pydantic import BaseModel, Field, conint

from utils.hr_search_engine import EmployeeSearchEngine

app = FastAPI(title="Employee Search API", version="2.0.0")

# --------------------------------------------------------------------------
# In‑memory registry of engines keyed by dataset_id
# --------------------------------------------------------------------------
ENGINES: Dict[str, EmployeeSearchEngine] = {}
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/tmp/employee_datasets"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------
class DatasetResponse(BaseModel):
    dataset_id: str


class SearchRequest(BaseModel):
    dataset_id: str = Field(..., description="ID obtained from /dataset upload")
    query: str = Field(..., description="Requirement / free‑text")
    skills: Optional[List[str]] = Field(None, description="Mandatory skill keywords")
    age_min: conint(ge=16, le=99) = 18  # type: ignore[valid-type]
    age_max: conint(ge=16, le=99) = 65  # type: ignore[valid-type]
    top_k: conint(ge=1, le=20) = 5      # type: ignore[valid-type]


class Candidate(BaseModel):
    name: str
    age: int
    skills: List[str]
    roles: str
    score: float
    justification: str


class SearchResponse(BaseModel):
    results: List[Candidate]


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/dataset", response_model=DatasetResponse, status_code=201)
async def upload_dataset(file: UploadFile = File(...)):
    """Accept an Excel file, build a vector index, return a dataset_id."""
    if not file.filename.lower().endswith(('.xls', '.xlsx')):
        raise HTTPException(status_code=415, detail="File must be .xls or .xlsx")

    # Save to disk so the engine can reload later if needed
    tmp_path = UPLOAD_DIR / f"{uuid.uuid4().hex}_{file.filename}"
    with tmp_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Build engine (may take a second for large files)
    try:
        engine = EmployeeSearchEngine(tmp_path)
    except Exception as exc:
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Failed to parse Excel: {exc}") from exc

    dataset_id = uuid.uuid4().hex[:8]
    ENGINES[dataset_id] = engine

    return {"dataset_id": dataset_id}


@app.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest):
    engine = ENGINES.get(req.dataset_id)
    if engine is None:
        raise HTTPException(status_code=404, detail="Unknown dataset_id. Upload a dataset first.")

    if req.age_min > req.age_max:
        raise HTTPException(status_code=400, detail="age_min cannot exceed age_max")

    raw = engine.search(
        query=req.query,
        skills=req.skills or [],
        age_min=req.age_min,
        age_max=req.age_max,
        top_k=req.top_k,
        return_json=False,
    )

    return {"results": raw}
