import re
import streamlit as st
import requests
from datetime import datetime

st.set_page_config(page_title="SCANOSS Workflow Trigger", page_icon="🧩", layout="wide")

# Header
st.title("SCANOSS Workflow Trigger")
st.caption("© EY Internal Use Only")

# ----------------------- Sidebar Config -----------------------
with st.sidebar:
    st.header("Repo Config")
    # Single field only (owner removed). Accepts either "owner/name" or just "name".
    repo_input = st.text_input("Repository (owner/name or name)", value="Universal-OSS-Compliance")
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

DEFAULT_OWNER = "Bharathnelle335"  # owner input removed; fallback owner

def owner_repo_from_repo_input(repo_input: str):
    """Accepts 'owner/name' or 'name'. Returns (owner, name)."""
    val = (repo_input or "").strip().strip("/")
    if "/" in val:
        o, n = val.split("/", 1)
        return o.strip(), n.strip()
    return DEFAULT_OWNER, val


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
    for run in runs:
        name = run.get("name") or run.get("display_title") or ""
        if client_run_id in name:
            return run
    return None

# --------- Git URL parsing + refs fetching ---------
GITHUB_RE = re.compile(r"https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/#?]+)(?:\.git)?(?:/(?:tree|commit|releases/tag)/(?P<ref>[^/#?]+))?", re.I)

def parse_git_url(url: str):
    """Return (owner, repo, ref_hint) if URL matches, else (None,None,None)."""
    if not url:
        return None, None, None
    m = GITHUB_RE.match(url.strip())
    if not m:
        # also accept 'owner/name'
        if "/" in url and not url.startswith("http"):
            owner, name = url.split("/", 1)
            return owner, name, None
        return None, None, None
    return m.group("owner"), m.group("repo").removesuffix('.git'), m.group("ref")


def fetch_refs(owner: str, repo: str, max_items: int = 100):
    branches_url = f"https://api.github.com/repos/{owner}/{repo}/branches"
    tags_url = f"https://api.github.com/repos/{owner}/{repo}/tags"
    branches = []
    tags = []
    try:
        rb = session.get(branches_url, params={"per_page": max_items}, timeout=60)
        if rb.ok:
            branches = [b.get("name") for b in rb.json() if isinstance(b, dict)]
        rt = session.get(tags_url, params={"per_page": max_items}, timeout=60)
        if rt.ok:
            tags = [t.get("name") for t in rt.json() if isinstance(t, dict)]
    except Exception:
        pass
    return branches, tags

# ----------------------- Main Form -----------------------
st.subheader("Dispatch inputs")
colA, colB = st.columns(2)

with colA:
    scan_type = st.selectbox("scan_type", ["docker", "git", "upload-zip", "upload-tar"], index=0)
    image_scan_mode = st.selectbox("image_scan_mode (for images)", ["manual", "syft"], index=0)
    enable_scanoss_bool = st.checkbox("enable_scanoss", value=True)
    enable_scanoss = "true" if enable_scanoss_bool else "false"

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
    git_url = st.text_input("git_url (e.g., https://github.com/user/repo or user/repo or .../tree/v1.2.3)")

    # Auto-detect branches/tags section
    st.markdown("**Auto-detect branches/tags**")
    ref_col1, ref_col2 = st.columns([1,1])
    with ref_col1:
        load_refs = st.button("🔄 Load branches/tags")
    detected_ref_hint = None
    owner_from_url, repo_from_url, ref_hint = parse_git_url(git_url)
    if ref_hint:
        detected_ref_hint = ref_hint

    if load_refs and owner_from_url and repo_from_url:
        branches, tags = fetch_refs(owner_from_url, repo_from_url)
        st.session_state["__branches__"] = branches
        st.session_state["__tags__"] = tags
        st.success(f"Loaded {len(branches)} branches and {len(tags)} tags from {owner_from_url}/{repo_from_url}")

    branches = st.session_state.get("__branches__", [])
    tags = st.session_state.get("__tags__", [])

    # Prefer branch selection first, then tag selection, then manual override
    sel_branch = sel_tag = manual_ref = ""
    if branches:
        sel_branch = st.selectbox("Select branch", [""] + branches, index=0)
    if tags:
        sel_tag = st.selectbox("Select tag", [""] + tags, index=0)

    manual_ref = st.text_input("Manual ref override (branch/tag/commit)", value=detected_ref_hint or "")

    # Decide final git_ref priority: manual > selected branch > selected tag > empty
    git_ref = manual_ref or sel_branch or sel_tag or ""

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
        owner, repo = owner_repo_from_repo_input(repo_input)
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
    owner, repo = owner_repo_from_repo_input(repo_input)
    runs = list_recent_runs(owner, repo, per_page=30)
    run = find_run_by_client_tag(runs, client_run_id)
    if not run:
        st.info("No recent run found with this client_run_id in its run name. It may still be starting.")
    else:
        name = run.get("name") or run.get("display_title")
        status = run.get("status")
        conclusion = run.get("conclusion")
        html_url = run.get("html_url")
        created = run.get("created_at")
        st.success(f"Found run: {name}")
        st.write(f"**Status:** {status}  |  **Conclusion:** {conclusion}  |  **Created:** {created}")
        if html_url:
            st.markdown(f"➡️ [Open in GitHub]({html_url})")

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
