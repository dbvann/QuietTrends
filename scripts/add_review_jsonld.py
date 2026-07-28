#!/usr/bin/env python3
"""Add visible author/date bylines and Product/Review JSON-LD to QuietTrends reviews."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {"index.html", "about.html", "methodology.html", "article-template.html"}

CATEGORY_AUTHORS = {
    "electronics": "Ethan Mercer",
    "computers": "Claire Bennett",
    "cell phones & accessories": "Marcus Hale",
    "home & kitchen": "Sophia Brooks",
    "kitchen & dining": "Ryan Cole",
    "patio, lawn & garden": "Olivia Hart",
    "tools & home improvement": "Ethan Mercer",
    "sports & outdoors": "Claire Bennett",
    "automotive": "Marcus Hale",
    "health & household": "Sophia Brooks",
    "beauty & personal care": "Ryan Cole",
    "baby": "Olivia Hart",
    "pet supplies": "Ethan Mercer",
    "office products": "Claire Bennett",
    "toys & games": "Marcus Hale",
    "video games": "Sophia Brooks",
    "musical instruments": "Ryan Cole",
    "camera & photo": "Olivia Hart",
    "industrial & scientific": "Ethan Mercer",
    "arts, crafts & sewing": "Claire Bennett",
    "clothing, shoes & jewelry": "Marcus Hale",
    "grocery & gourmet food": "Sophia Brooks",
    "handmade": "Ryan Cole",
    "books": "Olivia Hart",
    "audible": "Ethan Mercer",
}

CATEGORY_HINTS = [
    (("espresso", "coffee", "microwave", "air fryer", "mixer", "slushi"), "kitchen & dining"),
    (("speaker", "soundbar", "tv", "projector", "audio"), "electronics"),
    (("grill", "lawn", "mower", "outdoor", "pool", "garden", "sectional", "sofa"), "patio, lawn & garden"),
    (("fitness", "rack", "gym", "exoskeleton", "sauna"), "sports & outdoors"),
    (("face mask", "skincare", "beauty"), "beauty & personal care"),
    (("battery", "backup", "generator", "power"), "tools & home improvement"),
    (("vacuum", "air conditioner", "fridge"), "home & kitchen"),
]

BRANDS = {
    "dreame": "Dreame", "martha": "Martha Stewart", "philips": "Philips",
    "panasonic": "Panasonic", "jbl": "JBL", "major": "Major Fitness",
    "denon": "Denon", "dreo": "Dreo", "ninja": "Ninja", "igarden": "iGarden",
    "current": "Current", "acanva": "Acanva", "fellow": "Fellow",
    "hypershell": "Hypershell", "vestivium": "Vestivium", "hydragun": "HYDRAGUN",
    "irestore": "iRestore", "anker": "Anker", "sunseeker": "Sunseeker",
    "apolosign": "Apolosign", "bluetti": "BLUETTI", "backyard": "Backyard Discovery",
    "mammotion": "Mammotion", "beatbot": "Beatbot", "tcl": "TCL",
}


def first_commit_date(path: Path) -> date:
    rel = path.relative_to(ROOT).as_posix()
    try:
        output = subprocess.check_output(
            ["git", "log", "--follow", "--diff-filter=A", "--format=%cs", "--", rel],
            cwd=ROOT,
            text=True,
        ).strip().splitlines()
        if output:
            return date.fromisoformat(output[-1])
    except (subprocess.CalledProcessError, ValueError):
        pass
    return date.today()


def display_date(value: date) -> str:
    return f"{value.strftime('%B')} {value.day}, {value.year}"


def extract_category(soup: BeautifulSoup, product_name: str) -> str:
    node = soup.select_one(".article-sys-category")
    visible = node.get_text(" ", strip=True) if node else ""
    visible = re.sub(r"^PRODUCT REVIEW\s*[—-]\s*", "", visible, flags=re.I).strip().lower()
    for canonical in CATEGORY_AUTHORS:
        if canonical in visible:
            return canonical
    combined = f"{visible} {product_name}".lower()
    for keywords, canonical in CATEGORY_HINTS:
        if any(keyword in combined for keyword in keywords):
            return canonical
    return "home & kitchen"


def parse_byline(text: str) -> tuple[str | None, date | None]:
    author_match = re.search(r"By\s+(.+?)(?:\s*[•·|]\s*|$)", text, flags=re.I)
    author = author_match.group(1).strip() if author_match else None
    date_match = re.search(r"([A-Z][a-z]+\s+\d{1,2},\s+\d{4})", text)
    parsed = None
    if date_match:
        try:
            parsed = datetime.strptime(date_match.group(1), "%B %d, %Y").date()
        except ValueError:
            pass
    return author, parsed


def absolute_image(src: str) -> str:
    if src.startswith(("http://", "https://")):
        return src
    return "https://quiettrends.com/" + quote(src.lstrip("/"), safe="/%")


def process(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(original, "html.parser")
    title_node = soup.select_one("h1.article-title")
    if not title_node:
        return False

    title_text = title_node.get_text(" ", strip=True)
    product_name = re.sub(r"\s+Product Review\s*$", "", title_text, flags=re.I).strip()
    category = extract_category(soup, product_name)

    byline = soup.select_one(".article-byline")
    author = published = None
    if byline:
        author, published = parse_byline(byline.get_text(" ", strip=True))
    if not author:
        author = CATEGORY_AUTHORS[category]
    if not published:
        published = first_commit_date(path)

    if not byline:
        byline = soup.new_tag("p", attrs={"class": "article-byline"})
        byline.string = f"By {author}  •  {display_date(published)}"
        anchor = soup.select_one(".article-subtitle") or title_node
        anchor.insert_after(byline)
    else:
        byline.string = f"By {author}  •  {display_date(published)}"

    # Replace an existing QuietTrends Product JSON-LD block rather than duplicating it.
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        if '"@type": "Product"' in script.get_text() or '"@type":"Product"' in script.get_text():
            script.decompose()

    score_node = soup.select_one(".score-number")
    score = score_node.get_text(strip=True) if score_node else ""
    try:
        float(score)
    except ValueError:
        score = ""

    image_node = soup.select_one("img.article-main-img")
    image = absolute_image(image_node.get("src", "")) if image_node and image_node.get("src") else None

    amazon = soup.find("a", href=re.compile(r"amazon\.com/(?:dp|gp/product)/([A-Z0-9]{10})", re.I))
    asin = None
    if amazon:
        match = re.search(r"amazon\.com/(?:dp|gp/product)/([A-Z0-9]{10})", amazon.get("href", ""), re.I)
        asin = match.group(1).upper() if match else None

    first_word = re.sub(r"[^a-z0-9]", "", product_name.split()[0].lower()) if product_name else ""
    brand = BRANDS.get(first_word, product_name.split()[0] if product_name else "QuietTrends")
    canonical_url = f"https://quiettrends.com/{path.name}"

    review = {
        "@type": "Review",
        "name": title_text,
        "url": canonical_url,
        "author": {"@type": "Person", "name": author},
        "publisher": {"@type": "Organization", "name": "QuietTrends", "url": "https://quiettrends.com/"},
        "datePublished": published.isoformat(),
        "itemReviewed": {"@type": "Product", "name": product_name},
    }
    if score:
        review["reviewRating"] = {"@type": "Rating", "ratingValue": score, "bestRating": "10", "worstRating": "1"}

    product = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": product_name,
        "url": canonical_url,
        "brand": {"@type": "Brand", "name": brand},
        "review": review,
    }
    if image:
        product["image"] = image
    if asin:
        product["sku"] = asin

    script = soup.new_tag("script", attrs={"type": "application/ld+json"})
    script.string = json.dumps(product, ensure_ascii=False, indent=2)
    soup.head.append(script)

    rendered = "<!DOCTYPE html>\n" + str(soup)
    if rendered != original:
        path.write_text(rendered, encoding="utf-8")
        print(f"updated {path.name}: {author}, {published.isoformat()}, {asin or 'no ASIN'}")
        return True
    return False


def main() -> None:
    changed = 0
    for path in sorted(ROOT.glob("*.html")):
        if path.name in EXCLUDED:
            continue
        changed += int(process(path))
    print(f"Updated {changed} review pages.")


if __name__ == "__main__":
    main()
