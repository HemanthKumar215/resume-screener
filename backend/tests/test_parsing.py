from datetime import date

from screener.parsing import extract_contact, extract_education, extract_experience

TODAY = date(2026, 10, 1)

RESUME = """PRIYA NAIR
priya.nair@example.com | +91 98765 43210 | linkedin.com/in/priyanair | github.com/priyan
Experience
Software Engineer, Acme  Jan 2021 - Present
Intern, Beta  Jun 2020 – Dec 2020
Education
B.Tech Computer Science 2016 - 2020
"""


def test_experience_sums_ranges_and_ignores_education():
    exp = extract_experience(RESUME, TODAY)
    # Jun 2020 - Oct 2026 continuous = 6y 5m; the 2016-2020 degree must not count.
    assert exp.source == "dates"
    assert exp.years == 6.4


def test_overlapping_ranges_are_merged():
    text = "Job A Jan 2020 - Dec 2022\nJob B (part-time) Jan 2021 - Dec 2021"
    assert extract_experience(text, TODAY).years == 3.0


def test_numeric_month_format():
    assert extract_experience("Analyst 03/2022 - 02/2024", TODAY).years == 2.0


def test_claim_fallback():
    exp = extract_experience("Over 7+ years of professional experience in Java", TODAY)
    assert (exp.years, exp.source) == (7.0, "claim")


def test_no_experience():
    assert extract_experience("Fresh graduate eager to learn", TODAY).years == 0


def test_contact():
    c = extract_contact(RESUME)
    assert c.name == "Priya Nair"
    assert c.email == "priya.nair@example.com"
    assert c.phone == "+91 98765 43210"
    assert c.linkedin.endswith("linkedin.com/in/priyanair")
    assert c.github.endswith("github.com/priyan")


def test_name_falls_back_to_email():
    assert extract_contact("ravi.shankar99@example.com\nSkills: Python").name == "Ravi Shankar"


def test_education_levels():
    assert extract_education("M.Tech in CSE; B.Tech in ECE") == "Master's"
    assert extract_education("Bachelor of Science") == "Bachelor's"
    assert extract_education("PhD, Machine Learning") == "Doctorate"
    assert extract_education("Self-taught") == "None"
