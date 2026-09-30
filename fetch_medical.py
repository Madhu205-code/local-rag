from __future__ import annotations

import argparse
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
PUBMED_DB = "pubmed"
USER_AGENT = "local-rag/1.0 (personal offline medical RAG)"

TOPICS: dict[str, str] = {
    "lung-cancer-overview": "lung neoplasms[MeSH] AND (review[pt] OR systematic review[pt])",
    "nsclc": "non-small cell lung cancer",
    "sclc": "small cell lung cancer",
    "lung-cancer-screening": "lung cancer screening low dose CT",
    "lung-cancer-staging": "lung cancer TNM staging prognosis",
    "egfr-alk": "EGFR ALK ROS1 lung adenocarcinoma targeted therapy",
    "immunotherapy-cancer": "immune checkpoint inhibitor PD-1 PD-L1 cancer immunotherapy",
    "chemotherapy-regimens": "platinum doublet chemotherapy non-small cell lung cancer",
    "radiotherapy-lung": "stereotactic ablative radiotherapy lung cancer",
    "tumor-biology": "cancer hallmarks tumor microenvironment angiogenesis",
    "carcinogenesis": "carcinogenesis DNA damage mutation",
    "cancer-epidemiology": "cancer incidence epidemiology risk factors",
    "oncology-genomics": "next generation sequencing tumor genomics precision oncology",
    "pathology-diagnosis": "histopathology immunohistochemistry diagnosis",
    "radiology-chest": "chest radiology CT interpretation lung",
    "pulmonology": "COPD asthma interstitial lung disease pulmonary fibrosis",
    "pneumonia-infectious": "pneumonia tuberculosis respiratory infection",
    "cardiology": "hypertension coronary artery disease heart failure",
    "diabetes-metabolic": "type 2 diabetes mellitus insulin resistance metabolic syndrome",
    "neurology": "stroke epilepsy migraine neurodegenerative",
    "renal": "chronic kidney disease dialysis nephropathy",
    "pharmacology": "pharmacokinetics drug metabolism adverse drug reaction",
    "immunology": "immune system cytokines T cell B cell antibody",
    "infection-antibiotics": "antibiotic resistance bacterial infection treatment",
    "nutrition-metabolism": "nutrition obesity micronutrient vitamin deficiency",
    "epidemiology-biostatistics": "clinical trial cohort study statistical methods",
    "medical-ethics": "medical ethics informed consent patient autonomy",
    "clinical-diagnosis": "clinical diagnosis differential diagnosis physical examination",
    "health-informatics": "electronic health record clinical decision support machine learning",
    "nursing-care": "nursing care patient education chronic disease management",
}

MONTHS = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
    "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}


def fetch(url: str, retries: int = 4) -> bytes:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except Exception as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url[:120]}: {last}")


def esearch(term: str, retmax: int) -> list[str]:
    query = urllib.parse.urlencode(
        {
            "db": PUBMED_DB,
            "term": term,
            "retmax": retmax,
            "retmode": "json",
            "sort": "relevance",
        }
    )
    payload = fetch(f"{EUTILS}/esearch.fcgi?{query}").decode("utf-8", "replace")
    import json

    data = json.loads(payload)
    return data.get("esearchresult", {}).get("idlist", []) or []


def efetch(pmids: list[str]) -> list[dict]:
    if not pmids:
        return []
    query = urllib.parse.urlencode(
        {"db": PUBMED_DB, "id": ",".join(pmids), "retmode": "xml"}
    )
    root = ET.fromstring(fetch(f"{EUTILS}/efetch.fcgi?{query}"))
    records: list[dict] = []
    for article in root.findall(".//PubmedArticle"):
        record = parse_article(article)
        if record:
            records.append(record)
    return records


def _text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return re.sub(r"\s+", " ", "".join(node.itertext())).strip()


def parse_article(article: ET.Element) -> dict | None:
    pmid = _text(article.find(".//MedlineCitation/PMID"))
    title = _text(article.find(".//Article/ArticleTitle"))
    abstract_parts = [
        _text(node)
        for node in article.findall(".//Article/Abstract/AbstractText")
    ]
    abstract = " ".join(part for part in abstract_parts if part)
    if not abstract or not title:
        return None

    journal = _text(article.find(".//Article/Journal/Title")) or "unknown journal"
    year = _text(article.find(".//Article/Journal/JournalIssue/PubDate/Year"))
    if not year:
        medline_date = _text(article.find(".//Article/Journal/JournalIssue/PubDate/MedlineDate"))
        match = re.search(r"(\d{4})", medline_date)
        year = match.group(1) if match else "n.d."
    volume = _text(article.find(".//Article/Journal/JournalIssue/Volume"))
    issue = _text(article.find(".//Article/Journal/JournalIssue/Issue"))
    pages = _text(article.find(".//Article/Pagination/MedlinePgn"))

    keywords = [
        _text(node.find("DescriptorName")) or _text(node)
        for node in article.findall(".//MeshHeadingList/MeshHeading")
    ]
    keywords = [k for k in keywords if k][:12]
    author_line = ""
    authors = article.findall(".//Article/AuthorList/Author")
    if authors:
        names = []
        for person in authors[:6]:
            last = _text(person.find("LastName"))
            initials = _text(person.find("Initials"))
            if last:
                names.append(f"{last} {initials}".strip())
        if len(authors) > 6:
            names.append("et al.")
        author_line = ", ".join(names)

    doi = ""
    for node in article.findall(".//ArticleIdList/ArticleId"):
        if node.get("IdType") == "doi":
            doi = _text(node)

    return {
        "pmid": pmid,
        "title": title,
        "abstract": abstract,
        "journal": journal,
        "year": year,
        "volume": volume,
        "issue": issue,
        "pages": pages,
        "authors": author_line,
        "keywords": keywords,
        "doi": doi,
    }


def slugify(text: str, limit: int = 70) -> str:
    text = re.sub(r"[^A-Za-z0-9\s-]", " ", text)
    text = re.sub(r"\s+", "-", text.strip())
    return text[:limit].strip("-") or "untitled"


def write_record(record: dict, topic: str, out_dir: Path) -> Path:
    header = [
        f"TITLE: {record['title']}",
        f"AUTHORS: {record['authors'] or 'not listed'}",
        f"JOURNAL: {record['journal']}",
        f"YEAR: {record['year']}",
        f"VOLUME: {record['volume'] or 'n/a'}  ISSUE: {record['issue'] or 'n/a'}  PAGES: {record['pages'] or 'n/a'}",
        f"PMID: {record['pmid']}",
        f"DOI: {record['doi'] or 'n/a'}",
        f"TOPIC: {topic.replace('-', ' ')}",
    ]
    if record["keywords"]:
        header.append(f"KEYWORDS: {'; '.join(record['keywords'])}")
    header.append("")
    header.append(f"ABSTRACT: {record['abstract']}")

    folder = out_dir / topic
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{record['pmid']}_{slugify(record['title'])}.txt"
    path.write_text("\n".join(header), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Download a medical text corpus from PubMed.")
    parser.add_argument(
        "--out",
        default=str(Path.home() / "Downloads" / "medical-Rag" / "corpus-text"),
        help="output folder (default: ~/Downloads/medical-Rag/corpus-text)",
    )
    parser.add_argument("--per-topic", type=int, default=120)
    parser.add_argument("--limit-topics", type=int, default=0, help="0 = all topics")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    items = list(TOPICS.items())
    if args.limit_topics:
        items = items[: args.limit_topics]

    seen: set[str] = set()
    written = 0
    for index, (topic, term) in enumerate(items, start=1):
        try:
            pmids = [p for p in esearch(term, args.per_topic) if p not in seen]
        except Exception as exc:
            print(f"[{index}/{len(items)}] {topic}: search failed ({exc})")
            continue
        seen.update(pmids)
        saved = 0
        for start in range(0, len(pmids), 150):
            batch = pmids[start : start + 150]
            try:
                records = efetch(batch)
            except Exception as exc:
                print(f"    fetch failed at {start}: {exc}")
                time.sleep(1.0)
                continue
            for record in records:
                try:
                    write_record(record, topic, out_dir)
                    saved += 1
                except OSError:
                    continue
            time.sleep(0.4)
        written += saved
        print(f"[{index}/{len(items)}] {topic}: {saved} abstracts saved (running total {written})")

    readme = out_dir / "README.txt"
    readme.write_text(
        "Medical text corpus downloaded from PubMed via NCBI E-utilities.\n"
        f"Abstracts: {written}\n"
        "Each file is one abstract with title, authors, journal, year, PMID, DOI, MeSH keywords.\n"
        "Text-only. The CT scan images in this folder are NOT indexed by the text RAG.\n",
        encoding="utf-8",
    )
    print(f"done: {written} abstracts in {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
