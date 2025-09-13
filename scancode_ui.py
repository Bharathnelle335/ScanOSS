import streamlit as st
import requests
import time
from datetime import datetime, timezone
import uuid

"""
SCANOSS-only Workflow Trigger UI (Streamlit)
-------------------------------------------
This UI triggers your SCANOSS-only GitHub Actions workflow you just created.

✅ What it supports
- scan_type: docker | git | upload-zip | upload-tar
- docker_image (for docker)
- git_url + optional git_ref (for git; URL can include /tree/<ref> or /releases/tag/<tag>)
- archive_url (optional; remote .zip/.tar(.gz|.xz) used by upload-zip/upload-tar)
- client_run_id (opaque tag to help you find artifacts later)
- enable_scanoss toggle

🔐 Auth: put a GitHub Personal Access Token in `.streamlit/secrets.toml`:
[GITHUB]
TOKEN = "ghp_***"

🛠️ Configure OWNER/REPO/WORKFLOW_FILE/BRANCH below.
- WORKFLOW_FILE must match the YAML filename of your SCANOSS-only workflow in the repo.
"""

# ---------------- CONFIG ---------------- #
OWNER = "Bharathnelle335"              # e.g., "your-username-or-org"
REPO = "Universal-OSS-Compliance"      # e.g., "your-repo"
WORKFLOW_FILE = "oss-compliance-scanoss.yml"  # <-- update to the actual YAML filename you saved
BRANCH = "main"                         # repo default branch

GITHUB_TOKEN = st.secrets.get("GITHUB", {}).get("TOKEN", "")
if not GITHUB_TOKEN:
    st.warning("GitHub token not found in secrets. Add [GITHUB].TOKEN in .streamlit/secrets.toml")

API_ROOT = f"https://api.github.com/repos/{OWNER}/{REPO}"
HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
}

# --------------- Helpers --------------- #
def gh_post(url: str, payload: dict):
    r = requests.post(url, json=payload, headers=HEADERS, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"POST {url} failed: {r.status_code} {r.text}")
    return r

def gh_get(url: str, params: dict | None = None):
    r = requests.get(url, params=params or {}, headers=HEADERS, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"GET {url} failed: {r.status_code} {r.text}")
    return r.json()


def dispatch_workflow(inputs: dict):
    url = f"{API_ROOT}/actions/workflows/{WORKFLOW_FILE}/dispatches"
    payload = {"ref": BRANCH, "inputs": inputs}
    gh_post(url, payload)


def find_run_by_client_tag(client_tag: str, start_iso: str | None = None):
    """Try to locate the most recent run that matches our workflow + (optional) client tag.
       Fallback: pick the newest run created after start_iso.
    """
    try:
        runs_url = f"{API_ROOT}/actions/workflows/{WORKFLOW_FILE}/runs"
        data = gh_get(runs_url, params={"event": "workflow_dispatch", "per_page": 30})
        runs = data.get("workflow_runs", [])
        # Prefer a match by display_title containing our tag
        for run in runs:
            title = run.get("display_title") or run.get("name") or ""
            if client_tag and client_tag in title:
                return run
        # Fallback: first run newer than our start time
        if start_iso:
            start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
            newer = [r for r in runs if datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) >= start_dt]
            newer.sort(key=lambda r: r["created_at"], reverse=True)
            if newer:
                return newer[0]
        # Else latest
        if runs:
            return runs[0]
    except Exception as e:
        st.info(f"Could not list runs yet: {e}")
    return None


def poll_run_until_done(run_id: int, max_secs: int = 180):
    run_url = f"{API_ROOT}/actions/runs/{run_id}"
    status = "queued"
    conclusion = None
    start = time.time()
    placeholder = st.empty()
    while time.time() - start < max_secs:
        data = gh_get(run_url)
        status = data.get("status")
        conclusion = data.get("conclusion")
        html_url = data.get("html_url")
        placeholder.markdown(
            f"**Run status:** `{status}`  |  **conclusion:** `{conclusion}`  |  [Open in GitHub]({html_url})"
        )
        if status in {"completed"}:
            return data
        time.sleep(5)
    return gh_get(run_url)


def list_artifacts(run_id: int):
    url = f"{API_ROOT}/actions/runs/{run_id}/artifacts"
    return gh_get(url).get("artifacts", [])


# --------------- UI --------------- #
st.set_page_config(page_title="SCANOSS Workflow Trigger", layout="wide")
st.title("🔎 SCANOSS Compliance – GitHub Actions Trigger")
st.caption("For EY Internal Use Only • Triggers the SCANOSS-only workflow and fetches artifacts")

with st.sidebar:
    st.header("⚙️ Settings")
    owner = st.text_input("Owner", OWNER)
    repo = st.text_input("Repo", REPO)
    wf_file = st.text_input("Workflow file", WORKFLOW_FILE)
    branch = st.text_input("Branch", BRANCH)
    st.markdown("<hr>", unsafe_allow_html=True)
    enable_scanoss = st.toggle("Enable SCANOSS", True)

# Overwrite config if user edited sidebar
if owner != OWNER or repo != REPO or wf_file != WORKFLOW_FILE or branch != BRANCH:
    OWNER, REPO, WORKFLOW_FILE, BRANCH = owner, repo, wf_file, branch
    API_ROOT = f"https://api.github.com/repos/{OWNER}/{REPO}"

col1, col2 = st.columns([1,1])

with col1:
    scan_type = st.selectbox("Scan type", ["docker", "git", "upload-zip", "upload-tar"], index=0)
    client_run_id = st.text_input("Client run id (optional)", value=str(uuid.uuid4())[:8])

with col2:
    docker_image = git_url = git_ref = archive_url = ""
    if scan_type == "docker":
        docker_image = st.text_input("Docker image", placeholder="e.g., nginx:latest")
    elif scan_type == "git":
        git_url = st.text_input("Git URL", placeholder="https://github.com/user/repo or /tree/v1.2.3")
        git_ref = st.text_input("Git ref (optional)", placeholder="branch / tag / commit")
    elif scan_type in ("upload-zip", "upload-tar"):
        archive_url = st.text_input(
            "Remote archive URL (optional)",
            placeholder="https://example.com/source.tar.gz or source.zip",
            help="If omitted, your workflow expects a file in input/ (e.g., uploaded by another job)."
        )

st.markdown("---")

# Validate inputs
err = None
if scan_type == "docker" and not docker_image:
    err = "Docker image is required for docker scans"
elif scan_type == "git" and not git_url:
    err = "Git URL is required for git scans"

if err:
    st.error(err)

trigger = st.button("▶️ Trigger Workflow", disabled=bool(err or not GITHUB_TOKEN))

if trigger:
    inputs = {
        "scan_type": scan_type,
        "docker_image": docker_image or "",
        "git_url": git_url or "",
        "git_ref": git_ref or "",
        "enable_scanoss": str(bool(enable_scanoss)).lower(),
        "archive_url": archive_url or "",
        "client_run_id": client_run_id or "",
    }

    st.info("Dispatching workflow…")
    started_at = datetime.now(timezone.utc).isoformat()
    try:
        dispatch_workflow(inputs)
        st.success("Workflow dispatched ✅")
    except Exception as e:
        st.error(f"Dispatch failed: {e}")
    else:
        with st.spinner("Locating run and polling status…"):
            run = None
            # Try a short warm-up delay before searching
            time.sleep(4)
            run = find_run_by_client_tag(client_run_id, start_iso=started_at)
            if not run:
                st.warning("Run not found yet. Try the button below or check the Actions tab.")
            else:
                data = poll_run_until_done(run_id=run["id"], max_secs=240)
                st.subheader("Artifacts")
                arts = list_artifacts(run["id"]) if run else []
                if not arts:
                    st.write("No artifacts yet (or permissions required). Open the run to download:")
                    st.markdown(f"- [Open run in GitHub]({run.get('html_url')})")
                else:
                    for a in arts:
                        st.markdown(f"- **{a['name']}** · size ~{a.get('size_in_bytes', 0)} bytes · expires at {a.get('expires_at', '')}")
                    st.markdown(f"\n[Open run in GitHub]({run.get('html_url')}) for downloads (auth required).")

st.markdown("""
---
**Notes**
- Artifacts uploaded by the workflow follow the pattern: `oss-scan-results-${SCAN_LABEL}-${RUN_TAG}` and contain:
  - `scanoss_${SCAN_LABEL}.json`
  - `${SCAN_LABEL}_scanoss_components_report.xlsx`
  - `${SCAN_LABEL}_compliance_merged_report.xlsx`
- Make sure your repository has `SCANOSS_API_KEY` secret configured if your tenant requires it.
"""
)
