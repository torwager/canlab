"""Watch a Google Form's responses (via its linked, published-as-CSV response sheet) and open a GitHub issue for each new response.

One-time setup (form owner): in the form, Responses -> "Link to Sheets"; in that sheet, File -> Share -> Publish to web ->
choose the responses sheet and "Comma-separated values (.csv)" -> Publish; copy the URL and store it as the repository
secret FORM_CSV_URL. New rows are detected by their Timestamp column and remembered in data/form_seen.json.
"""
import csv, io, json, os, subprocess, sys, requests
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
SEEN = ROOT / "data" / "form_seen.json"
REPO = os.environ.get("GITHUB_REPOSITORY", "torwager/canlab")


def main():
    url = os.environ.get("FORM_CSV_URL")
    if not url:
        print("FORM_CSV_URL not set; nothing to do"); return 0
    r = requests.get(url, timeout=60); r.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(r.text)))
    seen = json.load(open(SEEN)) if SEEN.exists() else []
    key = lambda row: (row.get("Timestamp") or row.get("timestamp") or json.dumps(row, sort_keys=True))
    new = [row for row in rows if key(row) not in seen]
    label = os.environ.get("FORM_LABEL", "form-response")
    for row in new:
        body = "\n".join(f"**{k}**: {v}" for k, v in row.items() if v)
        title = f"New form response {key(row)}"
        if os.environ.get("GH_TOKEN"):
            subprocess.run(["gh", "issue", "create", "-R", REPO, "--title", title, "--label", label, "--body", body], check=False)
        else:
            print(title); print(body)
        seen.append(key(row))
    json.dump(seen, open(SEEN, "w"), indent=1)
    print(f"{len(rows)} responses, {len(new)} new")
    return 0


if __name__ == "__main__":
    sys.exit(main())
