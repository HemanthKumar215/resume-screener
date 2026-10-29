"""Explainable resume scoring.

Each candidate gets a 0-100 score built from weighted components (required skills, nice-to-have
skills, experience, education, keyword relevance). Every component reports what it found, so a
recruiter can see *why* a candidate ranked where they did. The score deliberately ignores name,
gender, age, photo and location.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import asdict
from datetime import date
from typing import Any

from .parsing import EDUCATION_RANK, extract_contact, extract_education, extract_experience
from .skills import canonicalize, extract_skills, match_skill, normalize

WEIGHTS = {
    "required_skills": 45,
    "nice_skills": 15,
    "experience": 20,
    "education": 5,
    "relevance": 15,
}

TIERS = [(80, "Strong match"), (65, "Good match"), (45, "Partial match"), (0, "Weak match")]

STOPWORDS = set(
    """a about above after again against all am an and any are as at be because been before being below between
    both but by can could did do does doing down during each few for from further had has have having he her here
    hers herself him himself his how i if in into is it its itself just me more most my myself no nor not now of
    off on once only or other our ours ourselves out over own same she should so some such than that the their
    theirs them themselves then there these they this those through to too under until up very was we were what
    when where which while who whom why will with would you your yours yourself yourselves etc using use used
    work worked working role team teams company years year experience strong good ability able looking candidate
    candidates responsibilities requirements required preferred plus must including within across new also well
    e.g i.e per via""".split()
)
_TOKEN = re.compile(r"[a-z][a-z0-9+#.]*[a-z0-9+#]|[a-z]")


def _terms(text: str) -> Counter[str]:
    tokens = [t for t in _TOKEN.findall(normalize(text)) if t not in STOPWORDS and len(t) > 1]
    bigrams = [f"{a} {b}" for a, b in zip(tokens, tokens[1:], strict=False)]
    return Counter(tokens + bigrams)


def keyword_relevance(job_text: str, resume_text: str) -> float:
    """Cosine similarity of log-scaled term frequencies (unigrams + bigrams), 0..1."""
    a, b = _terms(job_text), _terms(resume_text)
    if not a or not b:
        return 0.0
    wa = {t: 1 + math.log(c) for t, c in a.items()}
    wb = {t: 1 + math.log(c) for t, c in b.items()}
    dot = sum(w * wb[t] for t, w in wa.items() if t in wb)
    norm = math.sqrt(sum(w * w for w in wa.values())) * math.sqrt(sum(w * w for w in wb.values()))
    return dot / norm if norm else 0.0


def job_text(job: dict[str, Any]) -> str:
    parts = [job.get("title", ""), job.get("description", "")]
    parts += job.get("required_skills", []) + job.get("nice_to_have_skills", [])
    return "\n".join(p for p in parts if p)


def tier_for(score: int) -> str:
    return next(name for threshold, name in TIERS if score >= threshold)


def score_resume(job: dict[str, Any], resume_text: str, today: date | None = None) -> dict[str, Any]:
    required = _dedupe(job.get("required_skills") or [])
    nice = [s for s in _dedupe(job.get("nice_to_have_skills") or []) if s not in required]
    min_years = float(job.get("min_years") or 0)
    min_education = job.get("min_education") or "None"

    resume_norm = normalize(resume_text)
    found = extract_skills(resume_text)
    experience = extract_experience(resume_text, today)
    education = extract_education(resume_text)
    contact = extract_contact(resume_text)

    matched_req = [s for s in required if match_skill(s, found, resume_norm)]
    missing_req = [s for s in required if s not in matched_req]
    matched_nice = [s for s in nice if match_skill(s, found, resume_norm)]
    missing_nice = [s for s in nice if s not in matched_nice]

    raw_rel = keyword_relevance(job_text(job), resume_text)
    # Real resumes rarely exceed ~0.35 cosine against a JD; rescale so that's a full score.
    relevance = min(1.0, raw_rel / 0.35)

    components: list[dict[str, Any]] = []

    def add(key: str, label: str, value: float, detail: str) -> None:
        components.append(
            {"key": key, "label": label, "weight": WEIGHTS[key], "score": round(value, 3), "detail": detail}
        )

    if required:
        add(
            "required_skills",
            "Required skills",
            len(matched_req) / len(required),
            f"{len(matched_req)} of {len(required)} required skills",
        )
    if nice:
        add(
            "nice_skills",
            "Nice-to-have skills",
            len(matched_nice) / len(nice),
            f"{len(matched_nice)} of {len(nice)} nice-to-have skills",
        )
    if min_years > 0:
        exp_score = min(1.0, experience.years / min_years) if experience.years else 0.0
        add(
            "experience",
            "Experience",
            exp_score,
            f"{_fmt_years(experience.years)} found, {_fmt_years(min_years)} required"
            if experience.years
            else f"No experience dates found, {_fmt_years(min_years)} required",
        )
    if min_education != "None":
        need, have = EDUCATION_RANK.get(min_education, 0), EDUCATION_RANK.get(education, 0)
        add(
            "education",
            "Education",
            1.0 if have >= need else (0.5 if have == need - 1 else 0.0),
            f"{education if education != 'None' else 'No degree found'} (needs {min_education})",
        )
    add("relevance", "Keyword relevance", relevance, f"{round(relevance * 100)}% overlap with the job description")

    total_weight = sum(c["weight"] for c in components)
    score = round(sum(c["weight"] * c["score"] for c in components) / total_weight * 100) if total_weight else 0
    # Normalise weights to percentages of this job's total so the UI can show them directly.
    for c in components:
        c["weight"] = round(c["weight"] / total_weight * 100)

    highlights, concerns = _notes(
        required,
        matched_req,
        missing_req,
        matched_nice,
        experience.years,
        min_years,
        education,
        min_education,
        relevance,
    )

    return {
        "score": score,
        "tier": tier_for(score),
        "components": components,
        "matched_required": matched_req,
        "missing_required": missing_req,
        "matched_nice": matched_nice,
        "missing_nice": missing_nice,
        "skills_found": sorted(found),
        "experience": {"years": experience.years, "source": experience.source, "ranges": experience.ranges[:8]},
        "education": education,
        "contact": asdict(contact),
        "highlights": highlights,
        "concerns": concerns,
    }


def _notes(required, matched_req, missing_req, matched_nice, years, min_years, education, min_education, relevance):
    highlights: list[str] = []
    concerns: list[str] = []
    if required and not missing_req:
        highlights.append("Has every required skill")
    elif required and len(matched_req) / len(required) >= 0.75:
        highlights.append(f"Has {len(matched_req)} of {len(required)} required skills")
    if missing_req:
        concerns.append(
            "Missing " + _join(missing_req[:4]) + (f" and {len(missing_req) - 4} more" if len(missing_req) > 4 else "")
        )
    if matched_nice:
        highlights.append("Bonus: " + _join(matched_nice[:4]))
    if min_years > 0:
        if years >= min_years * 1.5:
            highlights.append(f"{_fmt_years(years)} of experience, well above the {_fmt_years(min_years)} asked")
        elif years >= min_years:
            highlights.append(f"Meets the experience bar ({_fmt_years(years)})")
        elif years == 0:
            concerns.append("Couldn't find work dates; check experience manually")
        else:
            concerns.append(f"{_fmt_years(years)} of experience, below the {_fmt_years(min_years)} asked")
    if min_education != "None" and EDUCATION_RANK.get(education, 0) < EDUCATION_RANK.get(min_education, 0):
        concerns.append(f"No {min_education} degree found")
    if relevance < 0.3:
        concerns.append("Low overlap with the job description wording")
    return highlights, concerns


def _dedupe(skills: list[str]) -> list[str]:
    out: list[str] = []
    for s in skills:
        c = canonicalize(s)
        if c and c not in out:
            out.append(c)
    return out


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _fmt_years(y: float) -> str:
    y = round(y, 1)
    n = int(y) if y == int(y) else y
    return f"{n} year" if n == 1 else f"{n} years"


def suggest_skills(description: str) -> list[str]:
    """Skills mentioned in a job description, to pre-fill the requirements form."""
    return sorted(extract_skills(description))
