"""Skill taxonomy: canonical skill names and the aliases that refer to them.

Matching is done on normalized text with custom word boundaries so that names like
"C++", "C#", ".NET" and "Node.js" match correctly and "Java" doesn't match "JavaScript".
"""

from __future__ import annotations

import re
from functools import lru_cache

# canonical name -> aliases (lowercase). The canonical name itself is always an alias.
SKILLS: dict[str, list[str]] = {
    # Languages
    "Python": ["python", "python3"],
    "Java": ["java", "core java", "java 8", "java 11", "java 17"],
    "JavaScript": ["javascript", "js", "ecmascript", "es6"],
    "TypeScript": ["typescript", "ts"],
    "C": ["c programming", "ansi c"],
    "C++": ["c++", "cpp"],
    "C#": ["c#", "csharp", "c sharp"],
    "Go": ["golang", "go lang"],
    "Rust": ["rust"],
    "Kotlin": ["kotlin"],
    "Swift": ["swift"],
    "PHP": ["php"],
    "Ruby": ["ruby"],
    "Scala": ["scala"],
    "R": ["r programming", "r language", "rstudio"],
    "SQL": ["sql", "t-sql", "pl/sql", "plsql"],
    "Bash": ["bash", "shell scripting", "shell script"],
    "Dart": ["dart"],
    # Frontend
    "React": ["react", "react.js", "reactjs", "react js"],
    "Angular": ["angular", "angularjs", "angular.js"],
    "Vue": ["vue", "vue.js", "vuejs"],
    "Next.js": ["next.js", "nextjs"],
    "Redux": ["redux"],
    "HTML": ["html", "html5"],
    "CSS": ["css", "css3", "scss", "sass"],
    "Tailwind CSS": ["tailwind", "tailwind css", "tailwindcss"],
    "Flutter": ["flutter"],
    "React Native": ["react native"],
    # Backend
    "Node.js": ["node.js", "nodejs", "node js", "node"],
    "Express": ["express", "express.js", "expressjs"],
    "Django": ["django"],
    "Flask": ["flask"],
    "FastAPI": ["fastapi", "fast api"],
    "Spring Boot": ["spring boot", "springboot", "spring"],
    ".NET": [".net", "dotnet", "asp.net", ".net core"],
    "GraphQL": ["graphql"],
    "REST APIs": ["rest api", "rest apis", "restful", "rest", "restful apis"],
    "Microservices": ["microservices", "micro-services", "microservice"],
    # Data stores
    "PostgreSQL": ["postgresql", "postgres", "psql"],
    "MySQL": ["mysql"],
    "MongoDB": ["mongodb", "mongo"],
    "Redis": ["redis"],
    "DynamoDB": ["dynamodb", "dynamo db"],
    "Elasticsearch": ["elasticsearch", "elastic search", "opensearch"],
    "Oracle": ["oracle db", "oracle database"],
    # Cloud & DevOps
    "AWS": ["aws", "amazon web services"],
    "Azure": ["azure", "microsoft azure"],
    "GCP": ["gcp", "google cloud", "google cloud platform"],
    "AWS Lambda": ["lambda", "aws lambda"],
    "Amazon S3": ["s3", "amazon s3", "aws s3"],
    "Amazon EC2": ["ec2", "amazon ec2", "aws ec2"],
    "Docker": ["docker", "containers", "containerization"],
    "Kubernetes": ["kubernetes", "k8s", "eks", "aks", "gke"],
    "Terraform": ["terraform", "opentofu"],
    "CI/CD": ["ci/cd", "cicd", "ci cd", "continuous integration", "continuous delivery", "continuous deployment"],
    "GitHub Actions": ["github actions"],
    "Jenkins": ["jenkins"],
    "Git": ["git", "github", "gitlab", "bitbucket"],
    "Linux": ["linux", "unix", "ubuntu"],
    "Ansible": ["ansible"],
    "Serverless": ["serverless"],
    # Data & ML
    "Machine Learning": ["machine learning", "ml"],
    "Deep Learning": ["deep learning", "neural networks", "neural network"],
    "TensorFlow": ["tensorflow", "keras"],
    "PyTorch": ["pytorch", "torch"],
    "scikit-learn": ["scikit-learn", "sklearn", "scikit learn"],
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "NLP": ["nlp", "natural language processing"],
    "Computer Vision": ["computer vision", "opencv", "image processing"],
    "LLMs": ["llm", "llms", "large language models", "generative ai", "genai", "gpt", "rag"],
    "Data Analysis": ["data analysis", "data analytics", "exploratory data analysis", "eda"],
    "Power BI": ["power bi", "powerbi"],
    "Tableau": ["tableau"],
    "Excel": ["excel", "ms excel", "microsoft excel", "advanced excel"],
    "Spark": ["spark", "pyspark", "apache spark"],
    "Airflow": ["airflow", "apache airflow"],
    "Kafka": ["kafka", "apache kafka"],
    "ETL": ["etl", "elt", "data pipelines", "data pipeline"],
    "Statistics": ["statistics", "statistical analysis", "hypothesis testing"],
    # Practices & tools
    "Agile": ["agile", "scrum", "kanban"],
    "Unit Testing": ["unit testing", "unit tests", "pytest", "jest", "junit", "tdd", "test-driven development"],
    "System Design": ["system design", "distributed systems", "scalable systems"],
    "Data Structures & Algorithms": ["data structures", "algorithms", "dsa"],
    "OOP": ["oop", "object oriented programming", "object-oriented programming", "object oriented design"],
    "Figma": ["figma"],
    "JIRA": ["jira"],
    # HR / business
    "Recruitment": ["recruitment", "recruiting", "talent acquisition", "sourcing"],
    "Communication": ["communication skills", "stakeholder management", "presentation skills"],
    "Leadership": ["leadership", "team lead", "mentoring", "people management"],
}

# Aliases that are common English words or substrings: only count them when the surrounding
# text makes the technical meaning clear (handled by requiring them to appear in a list-like
# context such as "Skills: Go, Rust" or capitalised in the original text).
AMBIGUOUS = {
    "go",
    "r",
    "c programming",
    "rest",
    "spring",
    "node",
    "lambda",
    "swift",
    "ruby",
    "rust",
    "dart",
    "express",
    "torch",
    "ml",
    "ts",
    "js",
    "git",
    "agile",
    "containers",
}

# Knowing the left-hand skill implies the right-hand one (e.g. Django experience means Python).
IMPLIES: dict[str, list[str]] = {
    "AWS Lambda": ["AWS", "Serverless"],
    "Amazon S3": ["AWS"],
    "Amazon EC2": ["AWS"],
    "DynamoDB": ["AWS"],
    "PostgreSQL": ["SQL"],
    "MySQL": ["SQL"],
    "Oracle": ["SQL"],
    "Next.js": ["React"],
    "Redux": ["React"],
    "Django": ["Python"],
    "Flask": ["Python"],
    "FastAPI": ["Python"],
    "Pandas": ["Python"],
    "PyTorch": ["Deep Learning", "Machine Learning"],
    "TensorFlow": ["Deep Learning", "Machine Learning"],
    "Deep Learning": ["Machine Learning"],
    "scikit-learn": ["Machine Learning"],
    "Spring Boot": ["Java"],
    "Express": ["Node.js"],
    "Kubernetes": ["Docker"],
    "GitHub Actions": ["CI/CD"],
    "Jenkins": ["CI/CD"],
}

_BOUNDARY_CHARS = r"a-z0-9+#"


def clean(text: str) -> str:
    """Unify dashes and collapse whitespace, keeping the original casing."""
    text = text.replace("\u2013", "-").replace("\u2014", "-").replace("\u00a0", " ")
    return re.sub(r"\s+", " ", text)


def normalize(text: str) -> str:
    return clean(text).lower()


@lru_cache(maxsize=1)
def _patterns() -> list[tuple[str, str, re.Pattern[str]]]:
    out = []
    for canonical, aliases in SKILLS.items():
        for alias in {canonical.lower(), *aliases}:
            # Custom boundaries: an alias must not be glued to letters, digits, '+' or '#'.
            # A trailing '.' is allowed (end of sentence) but '.js'-style suffixes are part of the alias.
            pattern = rf"(?<![{_BOUNDARY_CHARS}]){re.escape(alias)}(?![{_BOUNDARY_CHARS}]|\.[a-z])"
            out.append((canonical, alias, re.compile(pattern)))
    # Longest aliases first so "react native" is considered before "react".
    out.sort(key=lambda t: -len(t[1]))
    return out


def canonicalize(name: str) -> str:
    """Map a user-typed skill (e.g. 'k8s', 'reactjs') to its canonical name, or title-case it."""
    key = normalize(name).strip()
    for canonical, aliases in SKILLS.items():
        if key == canonical.lower() or key in aliases:
            return canonical
    return name.strip()


def extract_skills(text: str) -> set[str]:
    """Find canonical skills mentioned in text.

    Ambiguous aliases that are also everyday words (e.g. "Go", "R", "Rust", "Express") only
    count when they appear capitalised in the original text, which filters out phrases like
    "go to market" or "express interest".
    """
    original = clean(text)
    norm = original.lower()
    if len(norm) != len(original):  # exotic Unicode changed length when lowercased
        original = None
    found: set[str] = set()
    consumed: list[tuple[int, int]] = []
    for canonical, alias, pattern in _patterns():
        for m in pattern.finditer(norm):
            start, end = m.span()
            # Skip matches inside a longer alias already matched (e.g. "react" in "react native").
            if any(s <= start and end <= e for s, e in consumed):
                continue
            if alias in AMBIGUOUS and (original is None or not _looks_technical(original[start:end], alias)):
                continue
            found.add(canonical)
            consumed.append((start, end))
    # Add implied skills transitively.
    stack = list(found)
    while stack:
        for implied in IMPLIES.get(stack.pop(), []):
            if implied not in found:
                found.add(implied)
                stack.append(implied)
    return found


def _looks_technical(snippet: str, alias: str) -> bool:
    if alias in ("go", "r", "c programming"):
        return snippet[:1].isupper()
    if alias in ("js", "ts", "ml", "git"):
        return snippet.isupper() or snippet == "Git"
    return snippet[:1].isupper() or snippet.isupper()


def match_skill(skill: str, resume_skills: set[str], resume_norm: str) -> bool:
    """True if a required skill (canonical or free text) is present in the resume."""
    canonical = canonicalize(skill)
    if canonical in resume_skills:
        return True
    if canonical in SKILLS:
        return False
    # Unknown skill typed by the recruiter: fall back to a whole-phrase search.
    phrase = normalize(skill).strip()
    if not phrase:
        return False
    return re.search(rf"(?<![{_BOUNDARY_CHARS}]){re.escape(phrase)}(?![{_BOUNDARY_CHARS}])", resume_norm) is not None
