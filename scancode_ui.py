import re
import requests
import streamlit as st

# ===================== CONFIG ===================== #
OWNER = "Bharathnelle335"                # change if repo differs
REPO = "ScanCode_Toolkit"                # repo where workflow is stored
WORKFLOW_FILE = "scancode.yml"           # must match filename in .github/workflows/
BRANCH = "main"                          # update if different
TOKEN = st.secrets.get("GITHUB_TOKEN", "")  # store PAT in Streamlit secrets

HEADERS = {
    "Accept": "application/vnd.github+json",
    **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
}

st.set_page_config(page_title="ScanCode Toolkit Runner", layout="wide")
st.title("🧩 ScanCode Toolkit Runner")

if not TOKEN:
    st.warning("No GitHub token found. Add `GITHUB_TOKEN` to Streamlit secrets for private repos and higher rate limits.")

# ===================== HELPERS ===================== #
def normalize_github_url_and_ref(url: str, ref_input: str):
    """Normalize GH web URLs to .git and resolve ref from URL or explicit input."""
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
        return m.group(1), m.group(2).replace(".git", "")
    return None, None

def gh_get(url: str):
    return requests.get(url, headers=HEADERS, timeout=30)

def fetch_branches(owner: str, repo: str, per_page: int = 100):
    r = gh_get(f"https://api.github.com/repos/{owner}/{repo}/branches?per_page={per_page}")
    return [b["name"] for b in r.json()] if r.ok else []

def fetch_tags(owner: str, repo: str, per_page: int = 100):
    r = gh_get(f"https://api.github.com/repos/{owner}/{repo}/tags?per_page={per_page}")
    return [t["name"] for t in r.json()] if r.ok else []

# ===================== SESSION STATE (SAFE) ===================== #
for key, default in [
    ("git_ref_input", ""),
    ("_branches", []),
    ("_tags", []),
    ("ref_picker", "-- choose --"),
]:
    if key not in st.session_state:
        st.session_state[key] = default

def set_ref_from_picker():
    sel = st.session_state.get("ref_picker", "")
    if sel and sel != "-- choose --":
        st.session_state["git_ref_input"] = sel  # safe: callback updates the text_input key

# ===================== UI: SCAN TYPE ===================== #
scan_type = st.selectbox("Select Scan Type", ["repo", "folder", "zip", "tar", "docker"], index=0)

# ===================== UI: SIDE-BY-SIDE INPUTS ===================== #
if scan_type in ("repo", "folder"):
    c1, c2, c3 = st.columns([3, 2, 2])
    with c1:
        repo_url = st.text_input(
            "Repo URL",
            "https://github.com/psf/requests.git",
            key="repo_url_input",
            help="Supports web URLs like …/tree/<ref>, …/commit/<sha>, …/releases/tag/<tag>."
        )
    with c2:
        git_ref_input = st.text_input(
            "Git ref (branch/tag/commit)",
            key="git_ref_input",
            help="Examples: main, v1.2.3, 1a2b3c4"
        )
    with c3:
        folder_path = st.text_input(
            "Folder path (only for scan_type=folder)",
            "src/" if scan_type == "folder" else "",
            key="folder_path_input",
            disabled=(scan_type == "repo"),
            help="Relative path inside the repo (e.g., src/)."
        )

    # Optional: ref picker expander
    norm_url_preview, _, _ = normalize_github_url_and_ref(st.session_state.get("repo_url_input", ""), "")
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
                    on_change=set_ref_from_picker,  # safely updates git_ref_input
                )
        else:
            st.caption("Manual mode enabled — type directly in the Git ref box.")

    _norm_url, _resolved_ref, _meta = normalize_github_url_and_ref(st.session_state.get("repo_url_input", ""), st.session_state.get("git_ref_input", ""))
    st.caption(f"🔧 Repo URL (normalized): {_norm_url or '(none)'} | Ref: {_resolved_ref or '(none)'}")

elif scan_type == "zip":
    c1, c2 = st.columns([3, 2])
    with c1:
        archive_url = st.text_input("Archive URL (.zip)", "", placeholder="https://example.com/build.zip", key="archive_url_input")
    with c2:
        archive_file = st.text_input("Archive file (workspace)", "sample.zip", help="Used if URL is empty", key="archive_file_input")

elif scan_type == "tar":
    c1, _ = st.columns([3, 2])
    with c1:
        archive_url = st.text_input("Archive URL (.tar/.tar.gz/.tgz)", "", placeholder="https://example.com/src.tar.gz", key="archive_url_input")

elif scan_type == "docker":
    c1, _ = st.columns([3, 2])
    with c1:
        docker_image = st.text_input("Docker image", "alpine:latest", placeholder="nginx:latest", key="docker_image_input")

# ===================== UI: OPTIONS (SIDE-BY-SIDE) ===================== #
st.markdown("### Scan Options")
o1, o2, o3, o4, o5 = st.columns(5)
with o1:
    enable_license_scan = st.checkbox("License + Text", value=True, key="opt_license")
with o2:
    enable_metadata_scan = st.checkbox("Metadata (URLs/Info)", value=False, key="opt_meta")
with o3:
    enable_package = st.checkbox("Package Detect", value=True, key="opt_pkg")
with o4:
    enable_sbom_export = st.checkbox("Export SBOM", value=False, key="opt_sbom")
with o5:
    enable_copyright_scan = st.checkbox("Copyright/Author/Email", value=True, key="opt_copy")

# ===================== ACTION ===================== #
run = st.button("🚀 Start Scan", use_container_width=True)
if run:
    # Base inputs (always include scan_type + toggles; booleans as lowercase strings)
    inputs = {
        "scan_type": scan_type,
        "enable_license_scan": str(st.session_state["opt_license"]).lower(),
        "enable_metadata_scan": str(st.session_state["opt_meta"]).lower(),
        "enable_package": str(st.session_state["opt_pkg"]).lower(),
        "enable_sbom_export": str(st.session_state["opt_sbom"]).lower(),
        "enable_copyright_scan": str(st.session_state["opt_copy"]).lower(),
    }

    valid, err = True, None

    # Add ONLY the fields required for the chosen scan_type
    if scan_type in ("repo", "folder"):
        repo_url_val = st.session_state.get("repo_url_input", "")
        git_ref_val = st.session_state.get("git_ref_input", "")
        norm_repo_url, resolved_ref, _ = normalize_github_url_and_ref(repo_url_val, git_ref_val)
        if not norm_repo_url:
            valid, err = False, "repo_url is required for scan_type=repo/folder"
        else:
            inputs["repo_url"] = norm_repo_url
            if resolved_ref:
                inputs["git_ref"] = resolved_ref
        if scan_type == "folder":
            folder_path_val = (st.session_state.get("folder_path_input", "") or "").strip()
            if not folder_path_val:
                valid, err = False, "folder_path is required for scan_type=folder"
            else:
                inputs["folder_path"] = folder_path_val

    elif scan_type == "zip":
        url_val = (st.session_state.get("archive_url_input", "") or "").strip()
        file_val = (st.session_state.get("archive_file_input", "") or "").strip()
        if not url_val and not file_val:
            valid, err = False, "Provide archive_url or archive_file for scan_type=zip"
        else:
            if url_val: inputs["archive_url"] = url_val
            if file_val: inputs["archive_file"] = file_val

    elif scan_type == "tar":
        url_val = (st.session_state.get("archive_url_input", "") or "").strip()
        if not url_val:
            valid, err = False, "archive_url is required for scan_type=tar"
        else:
            inputs["archive_url"] = url_val

    elif scan_type == "docker":
        img_val = (st.session_state.get("docker_image_input", "") or "").strip()
        if not img_val:
            valid, err = False, "docker_image is required for scan_type=docker"
        else:
            inputs["docker_image"] = img_val

    # Guardrail: keep total input keys ≤ 10 for the API
    if valid and len(inputs) > 10:
        # If somehow exceeded (future fields), drop optional git_ref first
        if "git_ref" in inputs and len(inputs) > 10:
            inputs.pop("git_ref")
        # If still >10, drop enable_sbom_export next (least critical at dispatch time)
        if len(inputs) > 10 and "enable_sbom_export" in inputs:
            inputs.pop("enable_sbom_export")

    if not valid:
        st.error(f"❌ {err}")
    else:
        url = f"https://api.github.com/repos/{OWNER}/{REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches"
        payload = {"ref": BRANCH, "inputs": inputs}
        resp = requests.post(url, headers=HEADERS, json=payload)

        if resp.status_code == 204:
            st.success("✅ Scan started! Open Actions to watch progress.")
            st.markdown(f"[🔗 Open GitHub Actions](https://github.com/{OWNER}/{REPO}/actions)")
            with st.expander("Submitted Inputs", expanded=False):
                st.json(inputs)
        else:
            st.error(f"❌ Failed: {resp.status_code} {resp.text}")
