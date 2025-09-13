import streamlit as st
import requests
import time
from datetime import datetime, timedelta

"""
Streamlit UI to trigger your GitHub Actions workflow:
  name: OSS Compliance - SCANOSS (Docker/Git/Upload) • manual or syft

It calls the GitHub API `workflow_dispatch` with inputs that match your YAML.

Setup (Streamlit secrets):
- Add a file `.streamlit/secrets.toml` with:

  GITHUB_TOKEN = "ghp_xxx..."   # PAT with repo/workflow scopes

Run:
  streamlit run scanoss_actions_ui.py
"""

st.set_page_config(page_title="SCANOSS Workflow Trigger", page_icon="🧩", layout="wide")
st.title("🧩 SCANOSS Workflow Trigger (Docker / Git / Upload)")

# ----------------------- Sidebar Config -----------------------
with st.sidebar:
    st.header("Repo Config")
    owner = st.text_input("GitHub Owner", value="Bharathnelle335")
    repo = st.text_input("Repository", value="Universal-OSS-Compliance")
    workflow_file = st.text_input("Workflow file name", value="scancode.yml")
    ref = st.text_input("Ref (branch/tag)", value="main")

    st.markdown("---")
    st.caption("Auth: uses `st.secrets['GITHUB_TOKEN']`. Create a classic PAT with repo/workflow access.")

# ----------------------- Helpers -----------------------
TOKEN = st.secrets.get("GITHUB_TOKEN", "")
if not TOKEN:
    st.warning("⚠️ No GITHUB_TOKEN found in secrets. Add it to `.streamlit/secrets.toml` as GITHUB_TOKEN.")

session = requests.Session()
session.headers.update({
    "Accept": "application/vnd.github+json",
    "Authorization": f"Bearer {TOKEN}" if TOKEN else "",
    "X-GitHub-Api-Version": "2022-11-28",
})

def dispatch_workflow(owner: str, repo: str, workflow_file: str, ref: str, inputs: dict):
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/workflows/{workflow_file}/dispatches"
    payload = {"ref": ref, "inputs": inputs}
    r = session.post(url, json=payload, timeout=60)
    return r

def list_recent_runs(owner: str, repo: str, per_page: int = 20):
    url = f"https://api.github.com/repos/{owner}/{repo}/actions/runs"
    params = {"event": "workflow_dispatch", "per_page": per_page}
    r = session.get(url, params=params, timeout=60)
    if r.ok:
        return r.json().get("workflow_runs", [])
    return []

def find_run_by_client_tag(runs: list, client_run_id: str):
    client_run_id = (client_run_id or "").strip()
    if not client_run_id:
        return None
    # Search by name contains client_run_id or display_title contains it
    for run in runs:
        name = run.get("name") or run.get("display_title") or ""
        if client_run_id in name:
            return run
    return None

# ----------------------- Main Form -----------------------
st.subheader("Dispatch inputs")
colA, colB = st.columns(2)

with colA:
    scan_type = st.selectbox("scan_type", ["docker", "git", "upload-zip", "upload-tar"], index=0)
    image_scan_mode = st.selectbox("image_scan_mode (for images)", ["manual", "syft"], index=0)
    enable_scanoss_bool = st.checkbox("enable_scanoss", value=True)
    enable_scanoss = "true" if enable_scanoss_bool else "false"  # strings, to match your YAML conditions

with colB:
    client_run_id = st.text_input("client_run_id (optional tag)", value=datetime.utcnow().strftime("run-%Y%m%d-%H%M%S"))

# Conditional inputs
docker_image = ""
git_url = ""
git_ref = ""
archive_url = ""

if scan_type == "docker":
    docker_image = st.text_input("docker_image (e.g., nginx:latest)")
elif scan_type == "git":
    git_url = st.text_input("git_url (e.g., https://github.com/user/repo or .../tree/v1.2.3)")
    git_ref = st.text_input("git_ref (optional if included in git_url)", value="")
elif scan_type in ("upload-zip", "upload-tar"):
    st.caption("Provide a direct-download URL for the archive.")
    samples = {
        "ZIP sample": "https://github.com/actions/checkout/archive/refs/heads/main.zip",
        "TAR.GZ sample": "https://github.com/actions/checkout/archive/refs/heads/main.tar.gz",
    }
    use_sample = st.selectbox("Use a sample URL?", ["(none)"] + list(samples.keys()), index=0)
    if use_sample != "(none)":
        archive_url = samples[use_sample]
    archive_url = st.text_input("archive_url", value=archive_url)

# ----------------------- Submit -----------------------
col1, col2, col3 = st.columns([1,1,2])

with col1:
    go = st.button("🚀 Dispatch Workflow")
with col2:
    chk = st.button("🔎 Find My Run (by client_run_id)")

status_box = st.empty()

if go:
    # Validate minimal required inputs by scan_type
    err = None
    if scan_type == "docker" and not docker_image:
        err = "docker_image is required for scan_type=docker"
    if scan_type == "git" and not git_url:
        err = "git_url is required for scan_type=git"
    if scan_type in ("upload-zip", "upload-tar") and not archive_url:
        err = f"archive_url is required for scan_type={scan_type}"

    if err:
        status_box.error(err)
    else:
        inputs = {
            "scan_type": scan_type,
            "image_scan_mode": image_scan_mode,
            "docker_image": docker_image,
            "git_url": git_url,
            "git_ref": git_ref,
            "enable_scanoss": enable_scanoss,
            "archive_url": archive_url,
            "client_run_id": client_run_id,
        }
        try:
            r = dispatch_workflow(owner, repo, workflow_file, ref, inputs)
            if r.status_code in (201, 202, 204):
                status_box.success("✅ Dispatched! Open your repo's Actions tab to watch the run.")
            else:
                status_box.error(f"❌ Dispatch failed: {r.status_code} — {r.text}")
        except Exception as e:
            status_box.error(f"❌ Exception while dispatching: {e}")

if chk:
    runs = list_recent_runs(owner, repo, per_page=30)
    run = find_run_by_client_tag(runs, client_run_id)
    if not run:
        st.info("No recent run found with this client_run_id in its run name. It may still be starting.")
    else:
        rid = run.get("id")
        name = run.get("name") or run.get("display_title")
        status = run.get("status")
        conclusion = run.get("conclusion")
        html_url = run.get("html_url")
        created = run.get("created_at")
        st.success(f"Found run: {name}")
        st.write(f"**Status:** {status}  |  **Conclusion:** {conclusion}  |  **Created:** {created}")
        if html_url:
            st.markdown(f"➡️ [Open in GitHub]({html_url})")

        # list artifacts for this run
        art_url = run.get("artifacts_url")
        if art_url:
            try:
                ar = session.get(art_url, timeout=60)
                if ar.ok:
                    arts = ar.json().get("artifacts", [])
                    if arts:
                        st.subheader("Artifacts")
                        for a in arts:
                            st.write(f"• **{a.get('name')}**  (size: {a.get('size_in_bytes')} bytes, expired: {a.get('expired')})")
                            # GitHub does not give a public download link without auth; we can still provide the API link:
                            dl = a.get("archive_download_url")
                            if dl:
                                st.code(dl, language="text")
                    else:
                        st.caption("No artifacts on this run yet (or not uploaded).")
                else:
                    st.caption(f"Could not list artifacts: {ar.status_code}")
            except Exception as e:
                st.caption(f"Artifacts lookup error: {e}")

st.markdown("---")
st.caption("Tip: For `upload-zip` or `upload-tar`, provide a direct-download URL. For GitHub repos, you can use `.../archive/refs/heads/main.zip` or `.tar.gz`.")
