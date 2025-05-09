###############################################################################
#  HR Search – all-in-one container (FastAPI + Streamlit) – Python 3.12
###############################################################################
FROM python:3.12-slim AS runtime

# ── System setup ─────────────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

WORKDIR /app

# Install build tools for any wheels, then clean up
RUN apt-get update \
 && apt-get install --no-install-recommends -y build-essential \
 && pip install --upgrade pip

# ── Python deps ───────────────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install -r requirements.txt \
 && apt-get purge -y build-essential \
 && apt-get autoremove -y \
 && rm -rf /var/lib/apt/lists/*

# ── Application code ─────────────────────────────────────────────────────────
COPY . .

# ── Expose ports ─────────────────────────────────────────────────────────────
EXPOSE 8000 8501

# ── Entrypoint ────────────────────────────────────────────────────────────────
CMD bash -c "\
  uvicorn main:app --host 0.0.0.0 --port 8000 & \
  streamlit run ui_app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true \
"
