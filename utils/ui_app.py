# streamlit_app.py  –  minimal light-mode UI (auto-index, success count)
"""Streamlit front‑end for the Employee Search API – clean, auto‑indexing, and shows
how many candidates were found.

Key features
============
* **Auto‑index on upload** – drag&drop Excel and the vector index builds
  automatically.
* **Success banner** shows "Found N candidates" before rendering cards.
* **Placeholders** provide an example query & skills so users know the format.
* **Light‑mode only** – removes Streamlit chrome, deploy button, spinner GIF,
  sidebar, header, footer, emojis.

Run back‑end first::

    uvicorn main:app --reload --port 8000

Then launch UI::

    pip install streamlit requests
    streamlit run ui_app.py
"""
from __future__ import annotations

import io
import os
from typing import List

import requests
import streamlit as st


# ---------------------------------------------------------------------------
# Config – page + API endpoints
# ---------------------------------------------------------------------------
API_BASE = os.getenv("API_BASE", "http://localhost:8000")
UPLOAD_ENDPOINT = f"{API_BASE}/dataset"
SEARCH_ENDPOINT = f"{API_BASE}/search"

st.set_page_config(
    page_title="Employee Search Portal",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Global CSS – hide Streamlit chrome & style cards
# ---------------------------------------------------------------------------
HIDE_CSS = """
<style>
#MainMenu, footer, header {visibility: hidden;}
button[data-testid="baseButton-header"],
section[data-testid="stStatusWidget"],
section[data-testid="stSidebar"],
div[data-testid="collapsedControl"] {display: none !important;}
body {background-color: #fafafa;}
.card {background:#ffffff;border-radius:1rem;padding:1.5rem;
       box-shadow:0 4px 10px rgba(0,0,0,0.05);margin-bottom:1.5rem;}
.justify {text-align:justify;}
</style>
"""

st.markdown(HIDE_CSS, unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Helper functions – API calls
# ---------------------------------------------------------------------------


def upload_excel(file) -> str:
    files = {
        "file": (
            file.name,
            file,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    r = requests.post(UPLOAD_ENDPOINT, files=files, timeout=99)
    if r.status_code != 201:
        raise RuntimeError(r.json().get("detail", r.text))
    return r.json()["dataset_id"]


def search_api(dataset_id: str, query: str, skills: List[str], age_min: int, age_max: int, top_k: int):
    payload = {
        "dataset_id": dataset_id,
        "query": query,
        "skills": skills,
        "age_min": age_min,
        "age_max": age_max,
        "top_k": top_k,
    }
    try:
        r = requests.post(f"{API_BASE}/search", json=payload, timeout=30)
        r.raise_for_status()
    except requests.HTTPError as e:
        if r.status_code == 404 and "Unknown dataset_id" in r.text:
            st.warning("Backend lost the index – re-uploading your dataset…")
            _reupload_dataset()          # call your existing upload helper
            r = requests.post(f"{API_BASE}/search", json=payload, timeout=30)
            r.raise_for_status()
    r = requests.post(SEARCH_ENDPOINT, json=payload, timeout=99)
    if r.status_code != 200:
        raise RuntimeError(r.json().get("detail", r.text))
    return r.json()["results"]

# ──────────────────────────────────────────────────────────────────────────
# Helper: (re)upload the dataset and refresh dataset_id in session state
# ──────────────────────────────────────────────────────────────────────────
def _reupload_dataset() -> None:
    """
    Re-post the Excel file stored in session_state to /dataset
    and update session_state['dataset_id'].
    """
    if "dataset_file" not in st.session_state:
        st.error("Please upload a dataset first.")
        st.stop()

    file_bytes: bytes = st.session_state["dataset_file"]
    files = {
        "file": ("employees.xlsx", io.BytesIO(file_bytes),
                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    }

    r = requests.post(f"{API_BASE}/dataset", files=files, timeout=60)
    r.raise_for_status()
    st.session_state["dataset_id"] = r.json()["dataset_id"]
    
# ---------------------------------------------------------------------------
# Title
# ---------------------------------------------------------------------------

st.title("Employee Search Portal")

# ---------------------------------------------------------------------------
# Upload dataset – auto index
# ---------------------------------------------------------------------------

with st.expander("Upload dataset (Excel)", expanded="dataset_id" not in st.session_state):
    file_upl = st.file_uploader("Choose .xls or .xlsx file", type=["xls", "xlsx"], key="file_uploader")

    if (
        file_upl is not None
        and file_upl.name
        and st.session_state.get("dataset_id_for_file") != file_upl.name
    ):
        with st.spinner("Building index …"):
            try:
                ds_id = upload_excel(file_upl)
                st.session_state["dataset_id"] = ds_id
                st.session_state["dataset_id_for_file"] = file_upl.name
                st.success("Dataset uploaded and indexed.")
            except Exception as exc:
                st.error(str(exc))

if "dataset_id" not in st.session_state:
    st.stop()

# ---------------------------------------------------------------------------
# Search interface
# ---------------------------------------------------------------------------

st.subheader("Search candidates")

example_query = "ex. Analytics engineer to build scalable data models in Snowflake and dbt"
example_skills = "ex. snowflake, dbt"

query = st.text_input("Requirement / role description", placeholder=example_query)
skills_input = st.text_input("Mandatory skill keywords (comma-separated)", placeholder=example_skills)

c1, c2, c3 = st.columns(3)
with c1:
    age_min = st.number_input("Min age", 18, 99, 18)
with c2:
    age_max = st.number_input("Max age", 18, 99, 65)
with c3:
    top_k = st.slider("Top-K", 1, 20, 5)

if st.button("Search"):
    if not query.strip():
        st.warning("Please enter a requirement query.")
    elif age_min > age_max:
        st.warning("Min age cannot exceed max age.")
    else:
        skills = [s.strip() for s in skills_input.split(",") if s.strip()]
        with st.spinner("Searching …"):
            try:
                results = search_api(
                    st.session_state["dataset_id"],
                    query,
                    skills,
                    int(age_min),
                    int(age_max),
                    int(top_k),
                )
                if not results:
                    st.info("No candidates matched your criteria.")
                else:
                    st.success(f"Found {len(results)} candidate{'s' if len(results)!=1 else ''}.")
                    for rank, cand in enumerate(results, 1):
                        st.markdown(
                            f"<div class='card'>"
                            f"<h4>{rank}. {cand['name']} • {cand['age']} yrs</h4>"
                            f"<small><b>Skills:</b> {', '.join(cand['skills'])}</small><br>"
                            f"<small><b>Score:</b> {cand['score']:.2f}</small>"
                            f"<details><summary style='margin-top:0.5rem'>Details</summary>"
                            f"<p class='justify'><b>Roles / Responsibilities</b><br>{cand['roles']}</p>"
                            f"<p><b>Selection rationale:</b> {cand['justification']}</p>"
                            f"</details>"
                            f"</div>",
                            unsafe_allow_html=True,
                        )
            except Exception as exc:
                st.error(f"Search failed: {exc}")
