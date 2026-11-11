import json
import os
import sys
import urllib.request

def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: python scripts/web_search.py <query>")

    query = sys.argv[1]

    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    token    = os.environ.get("ANTHROPIC_AUTH_TOKEN")
    model    = os.environ.get("WEB_SEARCH_MODEL", "gemini-3.8-flash")

    missing = [k for k, v in [("ANTHROPIC_BASE_URL", base_url), ("ANTHROPIC_AUTH_TOKEN", token)] if not v]
    if missing:
        sys.exit(f"Missing environment variable(s): {', '.join(missing)}")

    url = base_url.rstrip("/") + "/v1/chat/completions"
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": query}],
        "web_search_options": {},
    }).encode()

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read())

    text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    print(text)

    citations = []
    for choice in data.get("choices", []):
        for ann in choice.get("message", {}).get("annotations", []):
            u = ann.get("url_citation", {}).get("url") or ann.get("url")
            if u:
                citations.append(u)

    if citations:
        print("\nCitations:")
        for u in citations:
            print(u)

if __name__ == "__main__":
    main()
