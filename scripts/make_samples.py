"""Generate the fictional sample resumes in samples/ (PDF + one DOCX).

pip install reportlab
python scripts/make_samples.py
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

OUT = Path(__file__).resolve().parent.parent / "samples"

RESUMES = [
    {
        "file": "ananya_iyer.pdf",
        "name": "Ananya Iyer",
        "contact": "ananya.iyer@example.com | +91 98450 11223 | linkedin.com/in/ananya-iyer-dev | github.com/ananyaiyer",
        "summary": "Backend engineer with 6 years of experience building serverless APIs on AWS.",
        "experience": [
            (
                "Senior Software Engineer, Finlytics",
                "Jan 2022 - Present",
                "Designed REST APIs in Python and FastAPI on AWS Lambda and API Gateway serving 2M requests a day. "
                "Modelled data in DynamoDB and PostgreSQL. Wrote all infrastructure in Terraform and shipped through "
                "GitHub Actions CI/CD. Cut p95 latency by 40% with Redis caching.",
            ),
            (
                "Software Engineer, CloudKart",
                "Jul 2019 - Dec 2021",
                "Built order-processing microservices in Python and Django, packaged with Docker and deployed to "
                "Amazon EKS (Kubernetes). Owned the SQL reporting layer and SQS-based async workflows.",
            ),
        ],
        "skills": "Python, FastAPI, Django, AWS (Lambda, S3, DynamoDB, SQS, API Gateway), Terraform, Docker, "
        "Kubernetes, PostgreSQL, Redis, REST APIs, GitHub Actions, Linux",
        "education": [("B.Tech, Computer Science, NIT Trichy", "2015 - 2019")],
    },
    {
        "file": "karthik_subramanian.pdf",
        "name": "Karthik Subramanian",
        "contact": "karthik.s@example.com | +91 99000 45678 | linkedin.com/in/karthik-subramanian",
        "summary": "Java platform engineer with 8+ years of experience in enterprise systems.",
        "experience": [
            (
                "Lead Engineer, Northwind Bank",
                "Mar 2020 - Present",
                "Led a team of 6 building Spring Boot microservices on Kubernetes. Migrated batch jobs from on-prem "
                "servers to Amazon EC2 and S3. Set up Jenkins pipelines and Oracle-to-PostgreSQL migration.",
            ),
            (
                "Software Engineer, InfoServe",
                "Jun 2017 - Feb 2020",
                "Developed Java REST APIs and SQL stored procedures for a claims platform. Mentored 3 juniors.",
            ),
        ],
        "skills": "Java, Spring Boot, Kubernetes, Docker, AWS EC2, Amazon S3, Jenkins, PostgreSQL, Oracle DB, SQL, "
        "REST APIs, Microservices, Leadership",
        "education": [
            ("M.Tech, Software Engineering, VIT Vellore", "2015 - 2017"),
            ("B.E., Information Technology, Anna University", "2011 - 2015"),
        ],
    },
    {
        "file": "rohan_verma.pdf",
        "name": "Rohan Verma",
        "contact": "rohan.verma@example.com | +91 98111 22334 | github.com/rohanverma",
        "summary": "Full-stack JavaScript developer who enjoys building product features end to end.",
        "experience": [
            (
                "Full Stack Developer, ShopSmart",
                "Aug 2022 - Present",
                "Built React and Next.js storefront features and Node.js/Express REST APIs backed by MongoDB. "
                "Deployed services with Docker on AWS EC2. Introduced Jest unit testing.",
            ),
            (
                "Frontend Intern, PixelWorks",
                "Jan 2022 - Jul 2022",
                "Implemented responsive UIs with HTML, CSS and Tailwind CSS from Figma designs.",
            ),
        ],
        "skills": "JavaScript, TypeScript, React, Next.js, Node.js, Express, MongoDB, HTML, CSS, Docker, AWS EC2, Git, Jest",
        "education": [("B.E., Computer Engineering, Pune University", "2018 - 2022")],
    },
    {
        "file": "meera_joshi.pdf",
        "name": "Meera Joshi",
        "contact": "meera.joshi@example.com | +91 97654 32109 | linkedin.com/in/meerajoshi",
        "summary": "Recent graduate passionate about cloud and backend development. AWS Certified Cloud Practitioner.",
        "experience": [
            (
                "Cloud Intern, DataNest",
                "Jan 2025 - Jun 2025",
                "Built a Python Flask REST API, containerised it with Docker and deployed it on AWS Lambda. "
                "Wrote SQL queries against PostgreSQL and set up a GitHub Actions pipeline.",
            ),
        ],
        "projects": "Expense tracker using Python, AWS S3 and DynamoDB. College event portal with Flask and MySQL.",
        "skills": "Python, Flask, SQL, PostgreSQL, MySQL, Docker, AWS, Git, Data Structures, OOP",
        "education": [("B.Tech, Information Technology, COEP Pune", "2021 - 2025")],
    },
    {
        "file": "sneha_kulkarni.pdf",
        "name": "Sneha Kulkarni",
        "contact": "sneha.kulkarni@example.com | +91 90040 77881",
        "summary": "Data analyst turning messy data into clear dashboards and business decisions.",
        "experience": [
            (
                "Data Analyst, RetailEdge",
                "Jun 2023 - Present",
                "Built Power BI dashboards for 40 stores and automated weekly reports with Python and Pandas. "
                "Wrote SQL queries for sales and inventory analysis and presented findings to stakeholders.",
            ),
        ],
        "skills": "SQL, Python, Pandas, Power BI, Excel, Tableau, Statistics, Data Analysis, Communication",
        "education": [("B.Sc, Statistics, Fergusson College", "2020 - 2023")],
    },
]

DOCX_RESUME = {
    "file": "arjun_reddy.docx",
    "lines": [
        "Arjun Reddy",
        "arjun.reddy@example.com | +91 91234 56780 | github.com/arjunreddy",
        "Summary",
        "Platform engineer with 5 years of experience automating cloud infrastructure.",
        "Experience",
        "DevOps Engineer, SkyScale  Apr 2021 - Present",
        "Manage AWS infrastructure with Terraform across 4 accounts. Run Kubernetes (EKS) clusters and "
        "Docker-based CI/CD pipelines in GitHub Actions. Wrote internal tooling in Python and Go.",
        "Systems Engineer, NetCore  Jul 2020 - Mar 2021",
        "Administered Linux servers and wrote Bash and Python automation scripts.",
        "Skills",
        "AWS, Terraform, Kubernetes, Docker, Python, Go, Bash, Linux, GitHub Actions, PostgreSQL, REST APIs",
        "Education",
        "B.Tech, Electronics and Communication, JNTU Hyderabad  2016 - 2020",
    ],
}

JOB = {
    "title": "Backend Engineer (Python, AWS)",
    "description": (
        "We're hiring a backend engineer to build and run the APIs behind our hiring platform. You'll design REST "
        "APIs in Python, run them on AWS (Lambda, API Gateway, DynamoDB, S3), write infrastructure as code, and own "
        "services from design to production. Experience with SQL databases and Docker is required. Terraform, "
        "DynamoDB, CI/CD and Kubernetes experience are a plus."
    ),
    "required_skills": ["Python", "AWS", "REST APIs", "SQL", "Docker"],
    "nice_to_have_skills": ["Terraform", "DynamoDB", "CI/CD", "Kubernetes"],
    "min_years": 3,
    "min_education": "Bachelor's",
    "alert_threshold": 80,
}


def make_pdf(r: dict) -> None:
    styles = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=styles["Heading2"], spaceBefore=8, spaceAfter=4)
    body = ParagraphStyle("b", parent=styles["BodyText"], leading=14)
    story = [Paragraph(r["name"], styles["Title"]), Paragraph(escape(r["contact"]), body), Spacer(1, 4 * mm)]
    story += [Paragraph("Summary", h), Paragraph(escape(r["summary"]), body)]
    story.append(Paragraph("Experience", h))
    for role, dates, desc in r["experience"]:
        story += [
            Paragraph(f"<b>{escape(role)}</b>  {escape(dates)}", body),
            Paragraph(escape(desc), body),
            Spacer(1, 2 * mm),
        ]
    if r.get("projects"):
        story += [Paragraph("Projects", h), Paragraph(escape(r["projects"]), body)]
    story += [Paragraph("Skills", h), Paragraph(escape(r["skills"]), body), Paragraph("Education", h)]
    for degree, dates in r["education"]:
        story.append(Paragraph(f"{escape(degree)}  {escape(dates)}", body))
    SimpleDocTemplate(
        str(OUT / r["file"]),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"{r['name']} - Resume",
    ).build(story)


def make_docx(r: dict) -> None:
    paras = "".join(f'<w:p><w:r><w:t xml:space="preserve">{escape(line)}</w:t></w:r></w:p>' for line in r["lines"])
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paras}</w:body></w:document>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/word/document.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="word/document.xml"/></Relationships>'
    )
    with zipfile.ZipFile(OUT / r["file"], "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", document)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for r in RESUMES:
        make_pdf(r)
    make_docx(DOCX_RESUME)
    (OUT / "job_backend_engineer.json").write_text(json.dumps(JOB, indent=2) + "\n")
    print(f"Wrote {len(RESUMES) + 1} resumes and a sample job to {OUT}")
