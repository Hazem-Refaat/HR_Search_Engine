from __future__ import annotations

import math
from pathlib import Path
from typing import List, Sequence, Dict, Any

import faiss
import pandas as pd
from sentence_transformers import SentenceTransformer


# --------------------------- CONFIGURATION -------------------------------- #
EMBEDDING_MODEL_PATH = "models/all-MiniLM-L6-v2"
ROLE_WEIGHT = 0.5
SKILL_WEIGHT = 0.3
AGE_WEIGHT = 0.2
TOP_K_RAW = 20  # initial FAISS retrieval size before re‑ranking
# -------------------------------------------------------------------------- #


def _age_score(age: int, min_age: int, max_age: int) -> float:
    """1.0 inside the range; otherwise a smooth exponential decay."""
    if min_age <= age <= max_age:
        return 1.0
    mid = (min_age + max_age) / 2.0
    return math.exp(-abs(age - mid) / 10.0)


def _skills_match_ratio(candidate_skills: set[str], required_keywords: set[str]) -> float:
    if not required_keywords:
        return 1.0
    if not required_keywords.issubset(candidate_skills):
        return 0.0
    return len(required_keywords) / max(len(candidate_skills), 1)


class EmployeeSearchEngine:
    """Encapsulates data loading, vector indexing, and querying logic."""

    def __init__(self, excel_path: str | Path):
        self.excel_path = Path(excel_path)
        self._df = self._load_and_prepare(self.excel_path)
        self._model = SentenceTransformer(EMBEDDING_MODEL_PATH)
        self._embeddings = self._model.encode(
            self._df["Employee Roles & Responsibilities"].tolist(),
            show_progress_bar=False,
            normalize_embeddings=True,
        ).astype("float32")
        self._faiss_index = faiss.IndexFlatIP(self._embeddings.shape[1])
        self._faiss_index.add(self._embeddings)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def search(
        self,
        query: str,
        skills: Sequence[str] | None = None,
        age_min: int = 18,
        age_max: int = 65,
        top_k: int = 5,
        return_json: bool = False,
    ) -> List[Dict[str, Any]]:
        """Return top‑*k* candidates best matching *query*.

        Parameters
        ----------
        query : str
            Natural‑language requirement.
        skills : list[str] | None
            Mandatory keywords that *must* be present in the candidate's skills.
        age_min, age_max : int
            Age filter.  Candidates outside the range are allowed but penalised.
        top_k : int
            How many candidates to return.
        return_json : bool
            If *True*, produce JSON‑serialisable dictionaries (default already is).

        Returns
        -------
        list[dict]
        """
        required_keywords = {s.strip().lower() for s in (skills or []) if s.strip()}
        query_vec = (
            self._model.encode([query], normalize_embeddings=True).astype("float32")
        )

        D, I = self._faiss_index.search(query_vec, TOP_K_RAW)
        idxs = I[0].tolist()
        sims = D[0].tolist()

        candidates: list[dict[str, Any]] = []
        for idx, sim in zip(idxs, sims):
            if idx == -1:
                continue
            row = self._df.iloc[idx]
            skill_set: set[str] = row["skill_set"]

            # Hard filter: skills (ALL keywords must be present)
            if required_keywords and not required_keywords.issubset(skill_set):
                continue

            skill_ratio = _skills_match_ratio(skill_set, required_keywords)
            age_s = _age_score(int(row["Employee Age"]), age_min, age_max)

            # ⬇️  NEW: skip candidates that fall outside the requested age range
            if not (age_min <= int(row["Employee Age"]) <= age_max):
                continue

            final_score = (
                ROLE_WEIGHT * sim
                + SKILL_WEIGHT * skill_ratio
                + AGE_WEIGHT  * age_s
            )
            candidates.append(
                {
                    "name": row["Employee Name"],
                    "age": int(row["Employee Age"]),
                    "skills": sorted(skill_set),
                    "roles": row["Employee Roles & Responsibilities"],
                    "score": float(final_score),
                    "justification": (
                        f"Role sim {sim:.2f}; "
                        + (
                            "all required skills present; " if required_keywords else ""
                        )
                        + f"age score {age_s:.2f}"
                    ),
                }
            )

        candidates.sort(key=lambda c: c["score"], reverse=True)
        return candidates[:top_k]

    # ------------------------------------------------------------------ #
    # Helper methods
    # ------------------------------------------------------------------ #
    @staticmethod
    def _load_and_prepare(path: Path) -> pd.DataFrame:
        df = pd.read_excel(path)
        required_cols = {
            "Employee Name",
            "Employee Skills",
            "Employee Age",
            "Employee Roles & Responsibilities",
        }
        missing = required_cols - set(df.columns)
        if missing:
            raise ValueError(f"Missing expected columns: {missing}")

        df = df.copy()
        df["skill_set"] = (
            df["Employee Skills"]
            .fillna("")
            .apply(lambda s: {k.strip().lower() for k in str(s).split(",") if k.strip()})
        )
        return df