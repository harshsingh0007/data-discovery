"""Licence and structured-metadata extraction from dataset landing pages."""
from __future__ import annotations

import json
import re

from .base import NotImplementedTool


def jsonld_datasets(html: str) -> list[dict]:
    """Return every schema.org Dataset object embedded as JSON-LD in a page.

    Many portals (Kaggle, Zenodo, data.gov, Hugging Face, Dataverse, CKAN sites) embed one.
    It is the most reliable machine-readable description of a dataset when it exists.
    """
    found = []
    for m in re.finditer(r"""(?is)<script[^>]*type=["']application/ld\+json["'][^>]*>(.*?)</script>""", html):
        try:
            data = json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        for item in items:
            if isinstance(item, dict) and "Dataset" in str(item.get("@type", "")):
                found.append(item)
    return found


def summarise_jsonld_dataset(d: dict) -> dict:
    """Keep the fields that matter for discovery, clipped for the model."""
    def name_of(v):
        if isinstance(v, list):
            return [name_of(x) for x in v][:5]
        if isinstance(v, dict):
            return v.get("name") or v.get("url") or v.get("@id")
        return v

    def clip(v, n=600):
        v = re.sub(r"<[^>]+>", " ", str(v)) if v is not None else None
        return None if v is None else (" ".join(v.split())[:n])

    dist = d.get("distribution") or []
    dist = dist if isinstance(dist, list) else [dist]
    return {
        "name": d.get("name"), "description": clip(d.get("description")),
        "license": d.get("license"), "creator": name_of(d.get("creator")), "publisher": name_of(d.get("publisher")),
        "datePublished": d.get("datePublished"), "dateModified": d.get("dateModified"),
        "temporalCoverage": d.get("temporalCoverage"), "spatialCoverage": name_of(d.get("spatialCoverage")),
        "isAccessibleForFree": d.get("isAccessibleForFree"), "keywords": clip(d.get("keywords"), 300),
        "variableMeasured": name_of(d.get("variableMeasured")),
        "distribution": [{k: x.get(k) for k in ("contentUrl", "encodingFormat", "fileFormat", "contentSize", "requiresSubscription", "name")
                          if isinstance(x, dict) and x.get(k) is not None} for x in dist[:10]],
    }


# ---------------------------------------------------------------------------
# LEARNER TODO (G1): find the licence of ANY dataset from its landing page
# ---------------------------------------------------------------------------
# Without this, every dataset link ends up LIC-UNKNOWN (a blocker) and verdicts are wrong.
#
# Contract (tests/test_learner_gaps.py::test_g1_* checks it):
#   extract_licence(html: str, jsonld: list[dict] | None = None) -> dict with EXACTLY these keys
#     licence_name : normalised name, one of e.g. "CC BY 4.0", "CC BY-SA 4.0", "CC BY-NC 4.0", "CC BY-NC-SA 4.0",
#                    "CC BY-ND 4.0", "CC0 1.0", "ODbL 1.0", "OGL v3.0", "MIT", "Apache-2.0"; None if not found
#                    or if the page says the licence is unknown/unspecified
#     licence_url  : the licence URL you found, or None
#     snippet      : the text or JSON-LD value you read it from (<= 400 chars), or None
#     found_in     : "json-ld" | "link" | "text" | None
#
# Order of evidence: JSON-LD "license" (string URL, or {"name", "url"}) first; then links to
# creativecommons.org / opendatacommons.org / nationalarchives.gov.uk (OGL) / choosealicense.com;
# then sentences such as "licensed under a Creative Commons Attribution 4.0 International (CC BY 4.0) license".
# jsonld defaults to jsonld_datasets(html) when None. Never guess: return None values when unsure.
def extract_licence(html: str, jsonld: list[dict] | None = None) -> dict:
    if jsonld is None:
        jsonld = jsonld_datasets(html)

    _null = {"licence_name": None, "licence_url": None, "snippet": None, "found_in": None}

    # --- URL → short name map ---------------------------------------------------
    _URL_PATTERNS = [
        (r"creativecommons\.org/licenses/by-nc-sa/(\d[\d.]*)", "CC BY-NC-SA {}"),
        (r"creativecommons\.org/licenses/by-nc-nd/(\d[\d.]*)", "CC BY-NC-ND {}"),
        (r"creativecommons\.org/licenses/by-nc/(\d[\d.]*)",    "CC BY-NC {}"),
        (r"creativecommons\.org/licenses/by-nd/(\d[\d.]*)",    "CC BY-ND {}"),
        (r"creativecommons\.org/licenses/by-sa/(\d[\d.]*)",    "CC BY-SA {}"),
        (r"creativecommons\.org/licenses/by/(\d[\d.]*)",       "CC BY {}"),
        (r"creativecommons\.org/(licenses/zero|publicdomain/zero)/(\d[\d.]*)", "CC0 {}"),
        (r"choosealicense\.com/licenses/cc0-(\d[\d.]*)",       "CC0 {}"),
        (r"opendatacommons\.org/licenses/odbl/(\d[\d.]*)",     "ODbL {}"),
        (r"opendatacommons\.org/licenses/pddl/(\d[\d.]*)",     "PDDL {}"),
        (r"opendatacommons\.org/licenses/odc-by/(\d[\d.]*)",   "ODC-By {}"),
        (r"nationalarchives\.gov\.uk/doc/open-government-licence/version/(\d+(?:\.\d+)?)", "OGL v{}"),
        (r"choosealicense\.com/licenses/mit",                  "MIT"),
        (r"choosealicense\.com/licenses/apache-2\.0",          "Apache-2.0"),
        (r"opensource\.org/licenses/MIT",                      "MIT"),
        (r"opensource\.org/licenses/Apache-2\.0",              "Apache-2.0"),
    ]

    _KNOWN_NAMES = {
        "cc by 4.0", "cc by 3.0", "cc by-sa 4.0", "cc by-nc 4.0", "cc by-nc-sa 4.0",
        "cc by-nd 4.0", "cc0 1.0", "cc0", "odbl 1.0", "ogl v3.0", "mit", "apache-2.0",
        "cc by-nc-nd 4.0",
    }

    def url_to_name(url: str) -> str | None:
        url = url or ""
        for pattern, template in _URL_PATTERNS:
            m = re.search(pattern, url, re.I)
            if m:
                version = next((g for g in m.groups() if g is not None), None)
                if version and "." not in version and "OGL" in template:
                    version = version + ".0"
                return template.format(version) if "{}" in template and version else template
        return None

    def name_matches(name: str) -> str | None:
        """Accept a JSON-LD licence name string if it looks like a known short name."""
        n = (name or "").strip()
        if n.lower() in _KNOWN_NAMES:
            return n
        # e.g. "Creative Commons Attribution 4.0" → try normalising
        if re.search(r"creative\s+commons", n, re.I):
            return n if len(n) <= 60 else None
        return None

    # 1. JSON-LD ------------------------------------------------------------------
    for d in jsonld:
        raw = d.get("license")
        if raw is None:
            continue
        snippet = None
        url = None
        name = None

        if isinstance(raw, str):
            snippet = raw[:400]
            derived = url_to_name(raw)
            if derived:
                name, url = derived, raw
            else:
                # Unknown or unrecognised string (e.g. Kaggle "Unknown Licence")
                return {"licence_name": None, "licence_url": None, "snippet": snippet, "found_in": "json-ld"}

        elif isinstance(raw, dict):
            url = raw.get("url") or None
            raw_name = raw.get("name") or ""
            snippet = (raw_name or url or "")[:400]
            derived = url_to_name(url or "")
            if derived:
                name = derived
            else:
                name = name_matches(raw_name)

        if name or url or snippet:
            return {"licence_name": name, "licence_url": url, "snippet": snippet, "found_in": "json-ld"}

    # 2. HTML <a href> to known licence domains -----------------------------------
    _LICENCE_DOMAINS = (
        "creativecommons.org/licenses", "creativecommons.org/publicdomain",
        "opendatacommons.org/licenses",
        "nationalarchives.gov.uk/doc/open-government-licence",
        "choosealicense.com/licenses",
        "opensource.org/licenses",
    )
    for m in re.finditer(r'<a\s[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html, re.I | re.S):
        href, text = m.group(1), re.sub(r"<[^>]+>", "", m.group(2)).strip()
        if any(d in href for d in _LICENCE_DOMAINS):
            name = url_to_name(href)
            snippet = (text or href)[:400]
            return {"licence_name": name, "licence_url": href, "snippet": snippet, "found_in": "link"}

    # 3. Text fallback ------------------------------------------------------------
    _TEXT_PATTERNS = [
        (r"CC[\s\-]BY[\s\-]NC[\s\-]SA[\s\-]([\d.]+)", "CC BY-NC-SA {}"),
        (r"CC[\s\-]BY[\s\-]NC[\s\-]ND[\s\-]([\d.]+)", "CC BY-NC-ND {}"),
        (r"CC[\s\-]BY[\s\-]NC[\s\-]([\d.]+)",          "CC BY-NC {}"),
        (r"CC[\s\-]BY[\s\-]SA[\s\-]([\d.]+)",           "CC BY-SA {}"),
        (r"CC[\s\-]BY[\s\-]ND[\s\-]([\d.]+)",           "CC BY-ND {}"),
        (r"CC[\s\-]BY[\s\-]([\d.]+)",                   "CC BY {}"),
        (r"CC0[\s\-]([\d.]+)",                           "CC0 {}"),
        (r"Creative Commons Zero",                       "CC0 1.0"),
        (r"ODbL[\s\-]([\d.]+)",                          "ODbL {}"),
        (r"Open Government Licen[cs]e.*?v?([\d.]+)",     "OGL v{}"),
    ]
    plain = re.sub(r"<[^>]+>", " ", html)
    for pattern, template in _TEXT_PATTERNS:
        m = re.search(pattern, plain, re.I)
        if m:
            version = m.group(1) if m.lastindex else None
            name = template.format(version) if "{}" in template and version else template
            snippet = plain[max(0, m.start() - 40): m.end() + 40].strip()[:400]
            return {"licence_name": name, "licence_url": None, "snippet": snippet, "found_in": "text"}

    return _null
