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

# ---------------- UI ---------------- #
st.title("🧩 ScanCode Toolkit Runner")

scan_type = st.selectbox("Select Scan Type", ["repo", "zip", "docker"], index=0)
repo_url = st.text_input("Repo URL (if scan_type = repo)", "https://github.com/psf/requests.git")
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
    inputs = {
        "scan_type": scan_type,
        "repo_url": repo_url,
        "archive_file": archive_file,
        "docker_image": docker_image,
        "enable_license_scan": str(enable_license_scan).lower(),
        "enable_copyright_scan": str(enable_copyright_scan).lower(),
        "enable_metadata_scan": str(enable_metadata_scan).lower(),
        "enable_package": str(enable_package).lower(),
        "enable_sbom_export": str(enable_sbom_export).lower(),
    }

    url = f"https://api.github.com/repos/{OWNER}/{REPO}/actions/workflows/{WORKFLOW_FILE}/dispatches"
    payload = {"ref": BRANCH, "inputs": inputs}
    resp = requests.post(url, headers=headers, json=payload)

    if resp.status_code == 204:
        st.success("✅ Scan started! It may take a few minutes.")

        # --- Pretty summary ---
        st.markdown("### 🔧 Selected Scan Options")
        st.write(f"- **Scan Type:** {scan_type}")
        if scan_type == "repo":
            st.write(f"- **Repo URL:** {repo_url}")
        elif scan_type == "zip":
            st.write(f"- **Archive File:** {archive_file}")
        elif scan_type == "docker":
            st.write(f"- **Docker Image:** {docker_image}")

        st.markdown("**Enabled Scans**")
        st.write(f"- {'✅' if enable_license_scan else '❌'} License Detection")
        st.write(f"- {'✅' if enable_copyright_scan else '❌'} Copyrights")
        st.write(f"- {'✅' if enable_metadata_scan else '❌'} Metadata Scan")
        st.write(f"- {'✅' if enable_package else '❌'} Package Detection")
        st.write(f"- {'✅' if enable_sbom_export else '❌'} SBOM Export")

        st.markdown("### 📂 View Results")
        st.write(f"[🔗 GitHub Actions Page](https://github.com/{OWNER}/{REPO}/actions)")

    else:
        st.error(f"❌ Failed to start scan: {resp.status_code} {resp.text}")
