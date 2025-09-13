import re
import streamlit as st
import requests

# ---------------- CONFIG ---------------- #
OWNER = "Bharathnelle335"                # change if repo differs
REPO = "ScanCode_Toolkit"                # repo where workflow is stored
WORKFLOW_FILE = "scancode.yml"           # must match filename in .github/workflows/
BRANCH = "main"                          # update if different
TOKEN = st.secrets.get("GITHUB_TOKEN", "")  # store PAT in Streamlit secrets

headers = {
    "Authorization": f"Bearer {TOKEN}" if TOKEN else "",
    "Accept": "application/vnd.github+json"
}

st.set_page_config(page_title="ScanCode Toolkit Runner", layout="wide")
st.title("🧩 ScanCode Toolkit Runner")

if not TOKEN:
    st.warning("No GitHub token found. Add `GITHUB_TOKEN` to Streamlit secrets for higher rate limits and private repos.")

# ---------------- Helpers ---------------- #
def normalize_github_url_and_ref(url: str, ref_input: str):
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
    m = re.search(r"github\.com/([^/]+)/([^/\.]+)(?:\.git)?$", url.strip().rstrip("/"))
    if not m:
        m = re.search(r"github\.com/([^/]+)/([^/]+)", url.strip())
    if m:
        return m.group(1), m.group(2).replace(".git","")
    return None, None

def gh_get(url: str):
    h = {"Accept": "application/vnd.github+json"}
    if TOKEN:
        h["Authorization"] = f"Bearer {TOKEN}"
    return requests.get(url, headers=h, timeout=30)

def fetch_branches(owner: str, repo: str, per_page: int = 100):
    r = gh_get(f"https://api.github.com/repos/{owner}/{repo}/branches?per_page={per_page}")
    if r.ok:
        return [b["name"] for b in r.json()]
    return []

def fetch_tags(owner: str, repo: str, per_page: int = 100):
    r = gh_get(f"https://api.github.com/repos/{owner}/{repo}/tags?per_page={per_page}")
    if r.ok:
        return [t["name"] for t in r.json()]
    return []

# ---------------- UI: Top row (side-by-side inputs) ---------------- #
scan_type = st.selectbox("Select Scan Type", ["repo", "folder", "zip", "tar", "docker"], index=0)

# state for ref input
if "git_ref_input" not in st.session_state:
    st.session_state.git_ref_input = ""

# Build the side-by-side row(s) depending on scan_type
if scan_type in ("repo", "folder"):
    c1, c2, c3 = st.columns([3, 2, 2])
    with c1:
        repo_url = st.text_input(
            "Repo URL",
            "https://github.com/psf/requests.git",
            help="Supports web URLs like …/tree/<ref>, …/commit/<sha>, …/releases/tag/<tag>."
        )
    with c2:
        git_ref_input = st.text_input("Git ref (branch/tag/commit)", key="git_ref_input", help="Examples: main, v1.2.3, 1a2b3c4")
    with c3:
        folder_path = st.text_input("Folder path (only for scan_type=folder)", "" if scan_type=="repo" else "src/")

    # Optional: Ref picker in an expander
    norm_url_preview, _, _ = normalize_github_url_and_ref(repo_url, "")
    owner, repo_name = parse_owner_repo(norm_url_preview)
    with st.expander("🔎 Pick ref (load tags/branches)", expanded=False):
        cols = st.columns([1, 1, 2])
        with cols[0]:
            load_refs = st.button("🔄 Load refs", use_container_width=True)
        with cols[1]:
            pick_mode = st.radio("From", ["Tags", "Branches", "Manual"], horizontal=True, index=0)
        if load_refs and owner and repo_name:
            st.session_state._branches = fetch_branches(owner, repo_name)
            st.session_state._tags = fetch_tags(owner, repo_name)
        elif "_branches" not in st.session_state:
            st.session_state._branches, st.session_state._tags = [], []
        if pick_mode in ("Tags", "Branches"):
            opts = st.session_state._tags if pick_mode == "Tags" else st.session_state._branches
            if not opts:
                st.warning("Click **Load refs** to fetch from GitHub.")
            else:
                sel = st.selectbox(f"Select {pick_mode[:-1].lower()}", options=["-- choose --"] + opts, index=0, key=f"sel_{pick_mode.lower()}")
                if sel != "-- choose --" and sel != st.session_state.git_ref_input:
                    st.session_state.git_ref_input = sel
                    st.rerun()

    # Preview normalization
    _norm_url, _resolved_ref, _meta = normalize_github_url_and_ref(repo_url, st.session_state.git_ref_input)
    st.caption(f"🔧 Repo URL (normalized): {_norm_url or '(none)'} | Ref: {_resolved_ref or '(none)'}")

elif scan_type == "zip":
    c1, c2 = st.columns([3, 2])
    with c1:
        archive_url = st.text_input("Archive URL (.zip)", "", placeholder="https://example.com/build.zip")
    with c2:
        archive_file = st.text_input("Archive file (workspace)", "sample.zip", help="Used if URL is empty")

elif scan_type == "tar":
    c1, _ = st.columns([3, 2])
    with c1:
        archive_url = st.text_input("Archive URL (.tar/.tar.gz/.tgz)", "", placeholder="https://example.com/src.tar.gz")

elif scan_type == "docker":
    c1, _ = st.columns([3, 2])
    with c1:
        docker_image = st.text_input("Docker image", "alpine:latest", placeholder="nginx:latest")

# ---------------- UI: Options row (side-by-side checkboxes) ---------------- #
st.markdown("### Scan Options")
o1, o2, o3, o4, o5 = st.columns(5)
with o1:
    enable_license_scan = st.checkbox("License + Text", value=True)
with o2:
    enable_metadata_scan = st.checkbox("Metadata (URLs/Info)", value=False)
with o3:
    enable_package = st.checkbox("Package Detect", value=True)
with o4:
    enable_sbom_export = st.checkbox("Export SBOM", value=False)
with o5:
    enable_copyright_scan = st.checkbox("Copyright/Author/Email", value=True)

# ---------------- ACTION ---------------- #
run = st.button("🚀 Start Scan", use_container_width=True)
if run:
    # Build inputs for dispatch
    inputs = {
        "scan_type": scan_type,
        "enable_license_scan": str(enable_license_scan).lower(),
        "enable_metadata_scan": str(enable_metadata_scan).lower(),
        "enable_package": str(enable_package).lower(),
        "enable_sbom_export": str(enable_sbom_export).lower(),
        "enable_copyright_scan": str(enable_copyright_scan).lower(),
        # include all keys expected by the workflow; blanks are fine
        "repo_url": "",
        "git_ref": "",
        "folder_path": "",
        "archive_url": "",
        "archive_file": "",
        "docker_image": "",
    }

    valid = True
    err = None

    if scan_type in ("repo", "folder"):
        norm_repo_url, resolved_ref, _ = normalize_github_url_and_ref(repo_url, st.session_state.git_ref_input)
        inputs["repo_url"] = norm_repo_url
        if resolved_ref:
            inputs["git_ref"] = resolved_ref
        if scan_type == "folder":
            inputs["folder_path"] = folder_path.strip()
            if not inputs["folder_path"]:
                valid, err = False, "folder_path is required for scan_type=folder"
        if not inputs["repo_url"]:
            valid, err = False, "repo_url is required for scan_type=repo/folder"

    elif scan_type == "zip":
        inputs["archive_url"] = (archive_url or "").strip()
        inputs["archive_file"] = (archive_file or "").strip()
        if not inputs["archive_url"] and not inputs["archive_file"]:
            valid, err = False, "Provide archive_url or archive_file for scan_type=zip"

    elif scan_type == "tar":
        inputs["archive_url"] = (archive_url or "").strip()
        if not inputs["archive_url"]:
            valid, err = False, "archive_url is required for scan_type=tar"

    elif scan_type == "docker":
        inputs["docker_image"] = (docker_image or "").strip()
        if not inputs["docker_image"]:
            valid, err = False, "docker_image is required for scan_type=docker"

    if not valid:
        st.error(f"❌ {err}")
    else:
        url = f"https://api.github.com/repos/{OWNER}/{REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches"
        payload = {"ref": BRANCH, "inputs": inputs}
        resp = requests.post(url, headers=headers, json=payload)

        if resp.status_code == 204:
            st.success("✅ Scan started! Open Actions to watch progress.")
            st.markdown(f"[🔗 Open GitHub Actions](https://github.com/{OWNER}/{REPO}/actions)")
            with st.expander("Submitted Inputs", expanded=False):
                st.json(inputs)
        else:
            st.error(f"❌ Failed: {resp.status_code} {resp.text}")

