import pytest

from screener.skills import canonicalize, extract_skills, match_skill, normalize


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Python, React.js and Node.js", {"Python", "React", "Node.js"}),
        ("C++ and C# on .NET", {"C++", "C#", ".NET"}),
        ("Deployed on k8s", {"Kubernetes", "Docker"}),
        ("React Native apps", {"React Native"}),
        ("JavaScript developer", {"JavaScript"}),
    ],
)
def test_extracts_canonical_skills(text, expected):
    assert expected <= extract_skills(text)


def test_java_does_not_match_javascript():
    assert "Java" not in extract_skills("Senior JavaScript engineer")


def test_ambiguous_words_need_capitals():
    assert extract_skills("We go to market and express interest in rust removal") == set()
    assert {"Go", "Rust", "Express"} <= extract_skills("Languages: Go, Rust. Built Express servers")


def test_implied_skills():
    found = extract_skills("Built APIs with Django on AWS Lambda backed by PostgreSQL")
    assert {"Python", "AWS", "Serverless", "SQL"} <= found


def test_canonicalize():
    assert canonicalize("k8s") == "Kubernetes"
    assert canonicalize("ReactJS") == "React"
    assert canonicalize("Underwater basket weaving") == "Underwater basket weaving"


def test_match_unknown_skill_by_phrase():
    text = "Experience with SAP SuccessFactors and Workday"
    assert match_skill("SAP SuccessFactors", extract_skills(text), normalize(text))
    assert not match_skill("Oracle HCM", extract_skills(text), normalize(text))
