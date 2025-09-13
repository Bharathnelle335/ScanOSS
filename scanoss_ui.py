import io
import re
import uuid
import requests
import streamlit as st
from datetime import datetime

# ===================== CONFIG ===================== #
OWNER = "Bharathnelle335"               # repo owner that hosts the workflow
REPO = "scanOSS"                         # repo that holds the SCANOSS workflow
WORKFLOW_FILE = "Scanoss.yml"            # exact filename under .github/workflows/
BRANCH = "main"                          # branch/tag where the workflow file exists
TOKEN = st.secrets.get("GITHUB_TOKEN", "")  # PAT with repo + workflow scopes

BASE = f"https://api.github.com/repos/{OWNER}/{REPO}"
HEADERS = {
    "Accept": "application/vnd.github+json",
    **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
    "X-GitHub-Api-Version": "2022-11-28",
}

# ===================== PAGE ===================== #
st.set_page_config(page_title="SCANOSS Workflow Trigger", page_icon="🧩", layout="wide")
st.title("🧩 SCANOSS Workflow Trigger")
st.caption("© EY Internal Use Only")

if not TOKEN:
    st.warning("No GitHub token found. Add `GITHUB_TOKEN` to Streamlit secrets for private repos and higher rate limits.")

# ===================== HELPERS ===================== #
def gh_get(url: str, **kw):
    return requests.get(url, headers=HEADERS, timeout=30, **kw)


def gh_post(url: str, payload: dict):
    return requests.post(url, headers=HEADERS, json=payload, timeout=60)


def fetch_branches(owner: str, repo: str, per_page: int = 100):
    r = gh_get(f"https://api.github.com/repos/{owner}/{repo}/branches?per_page={per_page}")
    return [b.get("name") for b in (r.json() if r.ok else []) if isinstance(b, dict) and b.get("name")] if r.ok else []


def fetch_tags(owner: str, repo: str, per_page: int = 100):
    r = gh_get(f"https://api.github.com/repos/{owner}/{repo}/tags?per_page={per_page}")
    return [t.get("name") for t in (r.json() if r.ok else []) if isinstance(t, dict) and t.get("name")] if r.ok else []


def normalize_github_url_and_ref(url: str, ref_input: str):
    """Normalize GH URLs to .git and resolve ref from URL or explicit input."""
    url = (url or "").strip()
    ref_in = (ref_input or "").strip()
    ref_in = ref_in.replace("refs/heads/", "").replace("refs/tags/", "")

    base_url = url
    detected_ref = ""
    if url.startswith("https://github.com/"):
        if "/tree/" in url:
            detected_ref = url.split("/tree/", 1)[1].split("/", 1)[0]
            base_url = url.split("/tree/", 1)[0]
        elif "/commit/" in url:
            detected_ref = url.split("/commit/", 1)[1].split("/", 1)[0]
            base_url = url.split("/commit/", 1)[0]
        elif "/releases/tag/" in url:
            detected_ref = url.split("/releases/tag/", 1)[1].split("/", 1)[0]
            base_url = url.split("/releases/tag/", 1)[0]
        if not base_url.endswith(".git"):
            base_url = base_url.rstrip("/") + ".git"

    resolved_ref = ref_in or detected_ref or ""
    return base_url, resolved_ref, {"parsed_from_url": bool(detected_ref), "detected_ref": detected_ref}


def parse_owner_repo(url: str):
    m = re.search(r"github\\.com/([^/]+)/([^/\\.]+)(?:\\.git)?$", url.strip().rstrip("/"))
    if not m:
        m = re.search(r"github\\.com/([^/]+)/([^/]+)", url.strip())
    if m:
        return m.group(1), m.group(2).replace(".git", "")
    return None, None


def list_workflow_runs(per_page=30):
    # Only runs for this workflow + branch + workflow_dispatch
    url = f"{BASE}/actions/workflows/{WORKFLOW_FILE}/runs"
    return gh_get(url, params={"per_page": per_page, "event": "workflow_dispatch", "branch": BRANCH})


def find_run_by_tag(runs: list, tag: str):
    for r in runs:
        title = r.get("display_title") or r.get("name") or ""
        if tag and tag in title:
            return r
    return runs[0] if runs else None


def get_run_artifacts(run_id: int):
    return gh_get(f"{BASE}/actions/runs/{run_id}/artifacts", params={"per_page": 100})


def download_artifact_zip(artifact_id: int) -> bytes:
    r = gh_get(f"{BASE}/actions/artifacts/{artifact_id}/zip", stream=True)
    if not r.ok:
        return b""
    return r.content


def new_client_tag() -> str:
    return datetime.utcnow().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]

# ===================== SESSION STATE ===================== #
for key, default in [
    ("git_ref_input", ""),
    ("_branches", []),
    ("_tags", []),
    ("ref_picker", "-- choose --"),
    ("last_client_run_id", ""),
]:
    if key not in st.session_state:
        st.session_state[key] = default


def set_ref_from_picker():
    sel = st.session_state.get("ref_picker", "")
    if sel and sel != "-- choose --":
        st.session_state["git_ref_input"] = sel

# ===================== UI: MODE + SIDE-BY-SIDE INPUTS ===================== #
scan_type = st.selectbox("scan_type", ["docker", "git", "upload-zip", "upload-tar"], index=0)

placeholders = {
    "git": "https://github.com/psf/requests",
    "upload-zip": "https://example.com/sample.zip  (or workspace path like sample.zip)",
    "upload-tar": "https://example.com/src.tar.gz  (or workspace path like src.tar.gz / .tar.xz)",
    "docker": "alpine:latest",
}
helps = {
    "git": "Repo URL. Supports pasting /tree/<ref>, /commit/<sha>, /releases/tag/<tag>.",
    "upload-zip": "ZIP via HTTP(S) URL (recommended) or a workspace file path (uploaded artifact).",
    "upload-tar": "TAR/TAR.GZ/TGZ/TAR.XZ via HTTP(S) URL (recommended) or workspace file path.",
    "docker": "Docker image name, e.g., alpine:latest or ghcr.io/org/image:tag.",
}

if scan_type == "git":
    c1, c2 = st.columns([3, 2])
    with c1:
        git_url = st.text_input("Source (Repo URL)", placeholders[scan_type], key="source_input", help=helps[scan_type])
    with c2:
        git_ref = st.text_input(
            "Git ref (branch/tag/commit)",
            key="git_ref_input",
            help="Leave empty to auto-detect from URL; fallback is 'main'.",
        )

    # Ref picker (matches reference layout)
    norm_url_preview, _, _ = normalize_github_url_and_ref(st.session_state.get("source_input", ""), "")
    owner, repo_name = parse_owner_repo(norm_url_preview)
    with st.expander("🔎 Pick ref (load tags/branches)", expanded=False):
        cols = st.columns([1, 1, 2])
        with cols[0]:
            load_refs = st.button("🔄 Load refs", use_container_width=True)
        with cols[1]:
            pick_mode = st.radio("From", ["Tags", "Branches", "Manual"], horizontal=True, index=0)

        if load_refs and owner and repo_name:
            st.session_state["_branches"] = fetch_branches(owner, repo_name)
            st.session_state["_tags"] = fetch_tags(owner, repo_name)

        if pick_mode in ("Tags", "Branches"):
            opts = st.session_state["_tags"] if pick_mode == "Tags" else st.session_state["_branches"]
            if not opts:
                st.warning("Click **Load refs** to fetch from GitHub.")
            else:
                st.selectbox(
                    f"Select {pick_mode[:-1].lower()}",
                    options=["-- choose --"] + opts,
                    index=0,
                    key="ref_picker",
                    on_change=set_ref_from_picker,
                )
        else:
            st.caption("Manual mode — type directly in the Git ref box above.")

    _norm_url, _resolved_ref, _meta = normalize_github_url_and_ref(
        st.session_state.get("source_input", ""), st.session_state.get("git_ref_input", "")
    )
    st.caption(f"🔧 Repo URL (normalized): {_norm_url or '(none)'} | Ref: {_resolved_ref or '(none)'}")

elif scan_type in ("upload-zip", "upload-tar"):
    c1, _ = st.columns([3, 2])
    with c1:
        archive_url = st.text_input("Source", placeholders[scan_type], key="source_input", help=helps[scan_type])
    git_ref = ""; git_url = st.session_state.get("source_input", ""); docker_image = ""
else:  # docker
    c1, _ = st.columns([3, 2])
    with c1:
        docker_image = st.text_input("Source", placeholders[scan_type], key="source_input", help=helps[scan_type])
    git_ref = ""; git_url = ""; archive_url = ""

# ===================== UI: OPTIONS (SIDE-BY-SIDE) ===================== #
st.markdown("### Scan options")
o1, o2, o3 = st.columns(3)
with o1:
    image_scan_mode = st.selectbox("image_scan_mode (for images)", ["manual", "syft"], index=0)
with o2:
    enable_scanoss_bool = st.checkbox("enable_scanoss", value=True)
with o3:
    client_run_id = st.text_input("client_run_id", value=st.session_state.get("last_client_run_id") or new_client_tag())
    st.session_state["last_client_run_id"] = client_run_id

enable_scanoss = "true" if enable_scanoss_bool else "false"

# ===================== DISPATCH ===================== #
run = st.button("🚀 Start Scan", use_container_width=True, type="primary")
if run:
    err = None
    if scan_type == "docker" and not st.session_state.get("source_input"):
        err = "docker_image is required for scan_type=docker"
    if scan_type == "git" and not st.session_state.get("source_input"):
        err = "git_url is required for scan_type=git"
    if scan_type in ("upload-zip", "upload-tar") and not st.session_state.get("source_input"):
        err = f"archive_url is required for scan_type={scan_type}"

    if err:
        st.error(f"❌ {err}")
    else:
        # Build inputs to match SCANOSS workflow
        inputs = {
            "scan_type": scan_type,
            "image_scan_mode": image_scan_mode,
            "docker_image": st.session_state.get("source_input") if scan_type == "docker" else "",
            "git_url": st.session_state.get("source_input") if scan_type == "git" else "",
            "git_ref": st.session_state.get("git_ref_input") if scan_type == "git" else "",
            "archive_url": st.session_state.get("source_input") if scan_type in ("upload-zip", "upload-tar") else "",
            "enable_scanoss": "true" if enable_scanoss_bool else "false",
            "client_run_id": client_run_id,
        }
        # Dispatch always against BRANCH where the workflow file exists
        payload = {"ref": BRANCH, "inputs": inputs}
        resp = gh_post(f"{BASE}/actions/workflows/{WORKFLOW_FILE}/dispatches", payload)
        if resp.status_code == 204:
            st.success("✅ Scan started!")
            with st.expander("Submitted Inputs", expanded=False):
                st.json(inputs)
        else:
            st.error(f"❌ Failed: {resp.status_code} {resp.text}")

# ===================== RESULTS: STATUS + DOWNLOAD ===================== #
st.markdown("---")
st.header("📦 Results")

res_c1, res_c2 = st.columns([3, 1])
with res_c1:
    result_tag = st.text_input("Run tag to check", value=st.session_state.get("last_client_run_id", ""))
with res_c2:
    check = st.button("🔎 Check status & fetch", use_container_width=True)

if check:
    if not result_tag:
        st.error("Provide a run tag (client_run_id).")
    else:
        runs_resp = list_workflow_runs(per_page=50)
        if not runs_resp.ok:
            st.error(f"Failed to list runs: {runs_resp.status_code} {runs_resp.text}")
        else:
            runs = runs_resp.json().get("workflow_runs", [])
            run = find_run_by_tag(runs, result_tag)
            if not run:
                st.warning("No run found yet for this tag. Try again shortly.")
            else:
                run_id = run["id"]
                status = run.get("status")
                conclusion = run.get("conclusion")
                started = run.get("run_started_at")
                html_url = run.get("html_url")
                st.write(f"**Run:** [{run_id}]({html_url})")
                st.write(f"**Status:** {status}  |  **Conclusion:** {conclusion or '—'}  |  **Started:** {started or '—'}")

                arts_resp = get_run_artifacts(run_id)
                if not arts_resp.ok:
                    st.error(f"Failed to list artifacts: {arts_resp.status_code} {arts_resp.text}")
                else:
                    artifacts = arts_resp.json().get("artifacts", [])
                    if not artifacts:
                        st.warning("No artifacts found for this run.")
                    else:
                        # Prefer artifact with tag in name; else the first
                        art = None
                        for a in artifacts:
                            if result_tag in a.get("name", ""):
                                art = a; break
                        if not art:
                            art = artifacts[0]
                        st.write(f"**Artifact:** `{art.get('name')}`  •  size ~ {art.get('size_in_bytes', 0)} bytes")
                        if not art.get("expired", False):
                            data = download_artifact_zip(art["id"])
                            if data:
                                fname = f"{art.get('name','scanoss-results')}.zip"
                                st.download_button("⬇️ Download ZIP", data=data, file_name=fname, mime="application/zip")
                            else:
                                st.error("Failed to download artifact zip (empty response).")
                        else:
                            st.error("Artifact expired (per repo retention). Re-run the scan.")
