import re
import streamlit as st
import requests

# ---------------- CONFIG ---------------- #
OWNER = "Bharathnelle335"   # change if repo differs
REPO = "ScanCode_Toolkit"   # repo where workflow is stored
WORKFLOW_FILE = "scancode.yml"  # must match filename in .github/workflows/
BRANCH = "main"             # update if different
TOKEN = st.secrets.get("GITHUB_TOKEN", "")  # store PAT in Streamlit secrets

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json"
}

# ---------------- Helpers ---------------- #
def normalize_github_url_and_ref(url: str, ref_input: str):
    """
    Returns (normalized_git_url, resolved_ref, meta)
    - Accepts:
        https://github.com/<owner>/<repo>.git
        https://github.com/<owner>/<repo>/tree/<ref>
        https://github.com/<owner>/<repo>/commit/<sha>
        https://github.com/<owner>/<repo>/releases/tag/<tag>
      → converts to https://github.com/<owner>/<repo>.git and extracts <ref>.
    - If ref_input is provided, it takes precedence after stripping refs/* prefixes.
    """
    url = (url or "").strip()
    ref_in = (ref_input or "").strip()
    # strip accidental full ref paths
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
        # ensure .git suffix
        if not base_url.endswith(".git"):
            base_url = base_url.rstrip("/") + ".git"

    # resolved ref: explicit > detected > ""
    resolved_ref = ref_in or detected_ref or ""
    meta = {"parsed_from_url": bool(detected_ref), "detected_ref": detected_ref, "normalized_url": base_url}
    return base_url, resolved_ref, meta

# ---------------- UI ---------------- #
st.title("🧩 ScanCode Toolkit Runner")

scan_type = st.selectbox("Select Scan Type", ["repo", "zip", "docker"], index=0)

repo_url = st.text_input(
    "Repo URL (if scan_type = repo)",
    "https://github.com/psf/requests.git",
    help="You can also paste web URLs like .../tree/<ref>, .../commit/<sha>, .../releases/tag/<tag>."
)

# Optional git ref (only show for repo)
git_ref_input = ""
if scan_type == "repo":
    git_ref_input = st.text_input(
        "Git ref (branch / tag / commit) — optional",
        "",
        help="Examples: main, v1.2.3, 1a2b3c4. Leave empty if your URL already has /tree/<ref> or /releases/tag/<tag>."
    )
    # Live normalization preview
    _norm_url, _resolved_ref, _meta = normalize_github_url_and_ref(repo_url, git_ref_input)
    with st.expander("🔎 Repo input normalization preview", expanded=False):
        st.write("**Repo URL (normalized):**", _norm_url or "(none)")
        st.write("**Ref (resolved):**", _resolved_ref or "(none)")
        if _meta.get("parsed_from_url"):
            st.info(f"Detected ref `{_meta.get('detected_ref')}` from the pasted URL.")

archive_file = st.text_input("Archive file (if scan_type = zip)", "sample.zip")
docker_image = st.text_input("Docker image (if scan_type = docker)", "alpine:latest")

st.markdown("### Select Scan Options")
enable_license_scan = st.checkbox("License + License Text Detection", value=True)
enable_copyright_scan = st.checkbox("Copyright + Author + Email Detection", value=True)
enable_metadata_scan = st.checkbox("Metadata (URLs + File Info)", value=False)
enable_package = st.checkbox("Package Detection", value=True)
enable_sbom_export = st.checkbox("Export SBOM (SPDX, CycloneDX)", value=False)

# ---------------- ACTION ---------------- #
if st.button("🚀 Start Scan"):
    # Normalize Git inputs (only if repo)
    norm_repo_url, resolved_ref, _ = (repo_url, "", {})
    if scan_type == "repo":
        norm_repo_url, resolved_ref, _ = normalize_github_url_and_ref(repo_url, git_ref_input)

    inputs = {
        "scan_type": scan_type,
        "repo_url": norm_repo_url if scan_type == "repo" else repo_url,
        "archive_file": archive_file,
        "docker_image": docker_image,
        "enable_license_scan": str(enable_license_scan).lower(),
        "enable_copyright_scan": str(enable_copyright_scan).lower(),
        "enable_metadata_scan": str(enable_metadata_scan).lower(),
        "enable_package": str(enable_package).lower(),
        "enable_sbom_export": str(enable_sbom_export).lower(),
    }
    # Only include git_ref if present (avoids 422 if workflow input not defined)
    if scan_type == "repo" and resolved_ref:
        inputs["git_ref"] = resolved_ref

    url = f"https://api.github.com/repos/{OWNER}/{REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches"
    payload = {"ref": BRANCH, "inputs": inputs}
    resp = requests.post(url, headers=headers, json=payload)

    if resp.status_code == 204:
        st.success("✅ Scan started! It may take a few minutes.")

        # --- Pretty summary ---
        st.markdown("### 🔧 Selected Scan Options")
        st.write(f"- **Scan Type:** {scan_type}")
        if scan_type == "repo":
            st.write(f"- **Repo URL (normalized):** {norm_repo_url}")
            st.write(f"- **Ref:** {resolved_ref or '(none)'}")
        elif scan_type == "zip":
            st.write(f"- **Archive File:** {archive_file}")
        elif scan_type == "docker":
            st.write(f"- **Docker Image:** {docker_image}")

        st.markdown("**Enabled Scans**")
        st.write(f"- {'✅' if enable_license_scan else '❌'} License Detection")
        st.write(f"- {'✅' if enable_copyright_scan else '❌'} Copyright")
        st.write(f"- {'✅' if enable_metadata_scan else '❌'} Metadata Scan")
        st.write(f"- {'✅' if enable_package else '❌'} Package Detection")
        st.write(f"- {'✅' if enable_sbom_export else '❌'} SBOM Export")

        st.markdown("### 📂 View Results")
        st.write(f"[🔗 GitHub Actions Page](https://github.com/{OWNER}/{REPO}/actions)")
    else:
        st.error(f"❌ Failed to start scan: {resp.status_code} {resp.text}")
