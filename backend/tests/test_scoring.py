from datetime import date

from screener.extract import extract_text
from screener.scoring import keyword_relevance, score_resume, suggest_skills, tier_for

TODAY = date(2026, 10, 29)


def _score_all(samples, job):
    out = {}
    for f in samples.iterdir():
        if f.suffix in (".pdf", ".docx"):
            text, _ = extract_text(f.read_bytes(), f.name)
            out[f.stem] = score_resume(job, text, TODAY)
    return out


def test_sample_ranking_is_sensible(samples, sample_job):
    r = _score_all(samples, sample_job)
    ranking = sorted(r, key=lambda k: -r[k]["score"])
    assert ranking[0] == "ananya_iyer"  # every required + nice-to-have skill
    assert ranking[-1] == "sneha_kulkarni"  # data analyst, missing AWS/REST/Docker
    assert r["ananya_iyer"]["tier"] == "Strong match"
    assert r["ananya_iyer"]["missing_required"] == []
    assert "Python" in r["karthik_subramanian"]["missing_required"]
    # Meera has every skill but only an internship: experience should hold her below the seniors.
    assert r["meera_joshi"]["score"] < r["ananya_iyer"]["score"]
    assert any("below" in c for c in r["meera_joshi"]["concerns"])


def test_components_are_weighted_and_explained(samples, sample_job):
    text, _ = extract_text((samples / "ananya_iyer.pdf").read_bytes(), "ananya_iyer.pdf")
    res = score_resume(sample_job, text, TODAY)
    keys = [c["key"] for c in res["components"]]
    assert keys == ["required_skills", "nice_skills", "experience", "education", "relevance"]
    assert sum(c["weight"] for c in res["components"]) == 100
    assert res["contact"]["email"] == "ananya.iyer@example.com"


def test_weights_redistribute_when_criteria_missing():
    job = {"title": "Python developer", "required_skills": ["Python"]}
    res = score_resume(job, "Python developer. Skills: Python", TODAY)
    assert [c["key"] for c in res["components"]] == ["required_skills", "relevance"]
    assert res["score"] >= 80


def test_empty_requirements_still_score():
    res = score_resume({"title": "Anything"}, "Some resume text", TODAY)
    assert 0 <= res["score"] <= 100


def test_tiers():
    assert [tier_for(s) for s in (95, 70, 50, 10)] == ["Strong match", "Good match", "Partial match", "Weak match"]


def test_relevance_bounds():
    assert keyword_relevance("", "anything") == 0
    assert keyword_relevance("python aws lambda", "python aws lambda") > 0.99


def test_suggest_skills():
    assert {"Python", "AWS", "Docker"} <= set(suggest_skills("We need Python on AWS with Docker"))
