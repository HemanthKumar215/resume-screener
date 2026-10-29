"""Pull structured facts out of resume text: contact details, experience, education."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
PRESENT = r"(?:present|current|now|till date|to date|ongoing)"
_MONTH = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sept?|oct|nov|dec)[a-z]*\.?"


def _point(n: str) -> str:
    """A date like "Jan 2020", "01/2020" or "2020"; groups are prefixed with n."""
    return rf"(?:(?P<{n}m>{_MONTH})\s*,?\s*|(?P<{n}mm>\d{{1,2}})\s*[/.-]\s*)?(?P<{n}y>(?:19|20)\d{{2}})"


DATE_RANGE = re.compile(
    _point("a") + r"\s*(?:-|to|until)\s*" + rf"(?:(?P<present>{PRESENT})|" + _point("b") + ")",
    re.IGNORECASE,
)
YEARS_CLAIM = re.compile(
    r"(\d{1,2}(?:\.\d)?)\s*\+?\s*(?:years?|yrs?)(?:\s+of)?(?:\s+(?:professional|industry|work|relevant|hands-on))?\s+(?:experience|exp)",
    re.IGNORECASE,
)
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s-]?)?(?:\(?\d{3,5}\)?[\s-]?)?\d{3,5}[\s-]?\d{4,5}(?!\d)")
LINKEDIN = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[A-Za-z0-9_-]+/?", re.IGNORECASE)
GITHUB = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[A-Za-z0-9_-]+/?", re.IGNORECASE)

EDUCATION_LEVELS = [
    (4, "Doctorate", r"\b(?:ph\.?\s?d|doctorate|doctor of philosophy)\b"),
    (3, "Master's", r"\b(?:m\.?\s?tech|m\.?\s?e\.|m\.?\s?sc|m\.?\s?s\.|msc|mba|mca|master(?:'s|s)?\b|m\.?\s?a\.)"),
    (
        2,
        "Bachelor's",
        r"\b(?:b\.?\s?tech|b\.?\s?e\.|b\.?\s?sc|bsc|bca|bba|b\.?\s?com|bachelor(?:'s|s)?\b|b\.?\s?a\.|b\.?\s?s\.)",
    ),
    (1, "Diploma", r"\b(?:diploma|associate degree)\b"),
]
EDUCATION_RANK = {name: rank for rank, name, _ in EDUCATION_LEVELS}
EDUCATION_RANK["None"] = 0


@dataclass
class Contact:
    name: str = ""
    email: str = ""
    phone: str = ""
    linkedin: str = ""
    github: str = ""


@dataclass
class Experience:
    years: float = 0.0
    source: str = "none"  # "dates", "claim" or "none"
    ranges: list[str] = field(default_factory=list)


def _to_month_index(year: str, month: str | None, numeric_month: str | None) -> int:
    m = 1
    if month:
        m = MONTHS.get(month[:3].lower(), 1)
    elif numeric_month and 1 <= int(numeric_month) <= 12:
        m = int(numeric_month)
    return int(year) * 12 + (m - 1)


def extract_experience(text: str, today: date | None = None) -> Experience:
    """Estimate years of experience.

    Prefers summing non-overlapping date ranges (e.g. "Jan 2020 - Present"), ignoring ranges
    that look like education. Falls back to an explicit claim like "5+ years of experience".
    """
    today = today or date.today()
    text = text.replace("\u2013", "-").replace("\u2014", "-")  # same length, so offsets still line up
    now_idx = today.year * 12 + today.month - 1
    intervals: list[tuple[int, int]] = []
    shown: list[str] = []

    edu_section = _education_spans(text)
    for m in DATE_RANGE.finditer(text):
        if any(s <= m.start() < e for s, e in edu_section):
            continue
        start = _to_month_index(m.group("ay"), m.group("am"), m.group("amm"))
        if m.group("present"):
            end = now_idx
        else:
            end = _to_month_index(m.group("by"), m.group("bm"), m.group("bmm"))
            if not (m.group("bm") or m.group("bmm")):
                end += 11 if not (m.group("am") or m.group("amm")) else 0
        end = min(end, now_idx)
        if end < start or end - start > 12 * 45:
            continue
        intervals.append((start, end + 1))
        shown.append(m.group(0).strip())

    total = 0
    for s, e in _merge(intervals):
        total += e - s
    years_from_dates = round(total / 12, 1)

    claims = [float(c) for c in YEARS_CLAIM.findall(text)]
    years_claimed = max(claims) if claims else 0.0

    if years_from_dates > 0:
        return Experience(years=years_from_dates, source="dates", ranges=shown)
    if years_claimed > 0:
        return Experience(years=years_claimed, source="claim")
    return Experience()


def _merge(intervals: list[tuple[int, int]]) -> list[tuple[int, int]]:
    merged: list[tuple[int, int]] = []
    for s, e in sorted(intervals):
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return merged


_SECTION = re.compile(
    r"^\s*(education|academic(?:s| background| qualifications)?|qualifications|experience|work experience|"
    r"professional experience|employment|projects|skills|technical skills|certifications|achievements|summary|"
    r"profile|internships?)\s*:?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _education_spans(text: str) -> list[tuple[int, int]]:
    """Character ranges covered by an Education section (so degree dates aren't counted as work)."""
    heads = list(_SECTION.finditer(text))
    spans = []
    for i, h in enumerate(heads):
        name = h.group(1).lower()
        if name.startswith(("education", "academic", "qualification")):
            end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
            spans.append((h.start(), end))
    return spans


def extract_education(text: str) -> str:
    low = text.lower()
    for _, name, pattern in EDUCATION_LEVELS:
        if re.search(pattern, low):
            return name
    return "None"


def extract_contact(text: str) -> Contact:
    c = Contact()
    if m := EMAIL.search(text):
        c.email = m.group(0)
    for m in PHONE.finditer(text):
        digits = re.sub(r"\D", "", m.group(0))
        if 10 <= len(digits) <= 13 and not re.fullmatch(r"(?:19|20)\d{2}(?:19|20)\d{2}", digits):
            c.phone = m.group(0).strip()
            break
    if m := LINKEDIN.search(text):
        c.linkedin = m.group(0).rstrip("/")
    if m := GITHUB.search(text):
        c.github = m.group(0).rstrip("/")
    c.name = _guess_name(text, c.email)
    return c


def _guess_name(text: str, email: str) -> str:
    """The first short line of letters near the top is almost always the candidate's name."""
    for line in text.splitlines()[:8]:
        line = line.strip()
        if not line or "@" in line or any(ch.isdigit() for ch in line):
            continue
        if _SECTION.match(line) or len(line) > 40:
            continue
        words = line.replace(",", " ").split()
        if 1 < len(words) <= 4 and all(re.fullmatch(r"[A-Za-z][A-Za-z.'-]*", w) for w in words):
            return " ".join(w if w.isupper() and len(w) <= 2 else w.title() for w in words)
    if email:
        local = re.sub(r"[\d_]+", " ", email.split("@")[0]).replace(".", " ").strip()
        if local:
            return " ".join(p.title() for p in local.split())
    return ""
