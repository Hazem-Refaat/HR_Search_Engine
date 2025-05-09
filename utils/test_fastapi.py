import requests, json, pathlib

base = "http://localhost:8000"

# 1️⃣ upload again and capture the id
xlsx_path = pathlib.Path("data/sample_employee_data_1000.xlsx")
r = requests.post(f"{base}/dataset", files={"file": xlsx_path.open("rb")})
r.raise_for_status()           # <- will throw if upload failed
dataset_id = r.json()["dataset_id"]
print("Dataset ID:", dataset_id)

# 2️⃣ run a query with that id
payload = {
    "dataset_id": dataset_id,
    "query": "Analytics engineer—Snowflake & dbt",
    "skills": ["snowflake", "dbt"],
    "age_min": 30,
    "age_max": 50,
    "top_k": 5
}
res = requests.post(f"{base}/search", json=payload)
print("Status:", res.status_code, res.reason)
print("Body:\n", json.dumps(res.json(), indent=2))
