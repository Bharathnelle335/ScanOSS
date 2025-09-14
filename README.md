# SCANOSS Workflow Docs

## 1) Why this workflow exists (what it’s for)

This workflow lets you run **open-source component & license discovery** against:

* a **Docker image**,
* a **Git repository** (branch / tag / commit),
* or an **uploaded archive** (.zip / .tar/.tgz/.txz)

It’s built for **CI-friendly, reproducible scans** that produce artifacts you can download and review offline.
Out of the box it generates:

* **SCANOSS detections** in JSON (components, versions, licenses)
* **Excel summaries** for quick review:

  * `<label>_scanoss_components_report.xlsx`
  * `<label>_compliance_merged_report.xlsx`
* **(Optional via Syft in this workflow)** SBOMs:

  * SPDX JSON: `sbom_<label>.spdx.json`
  * CycloneDX (JSON & XML): `sbom_<label>.cdx.json`, `sbom_<label>.cdx.xml`
  * **Layer map CSV** for container images: `component_layer_map.csv`

> Note: SCANOSS **Workbench** (GUI) can export SPDX/CycloneDX interactively, but it doesn’t expose a headless CI API. This workflow therefore uses the **SCANOSS CLI** for detections, and Syft to produce SBOMs & layer provenance inside CI.

---

## 2) How our workflow works (what it does under the hood)

**High-level flow**

1. **Inputs** (from the “Run workflow” form):

   * `scan_type` = `docker` | `git` | `upload-zip` | `upload-tar`
   * `image_scan_mode` = `manual` | `syft` (affects how images are scanned by SCANOSS)
   * `docker_image` | `git_url` + `git_ref` | `archive_url`
   * `enable_scanoss` (bool) and `client_run_id` (tag for artifact naming)
2. **Source prep**

   * **docker**: normalize & pull the image.
   * **git**: normalize GitHub URLs (`/tree/`, `/commit/`, `/releases/tag/`), shallow clone if branch/tag, else full clone + detached checkout (commit SHA).
   * **upload-zip/tar**: download and extract archive.
   * **Auto-build** (git/zip/tar): if a `Dockerfile` is found, try building a temporary image (gives you an image target for container-style scans).
3. **SCANOSS scan**

   * If `enable_scanoss=true`:

     * **Docker + manual**: export image filesystem (`docker export`) and run `scanoss-py scan` on the unpacked rootfs.
     * **Docker + syft**: run `scanoss-py container-scan IMAGE` (SCANOSS uses Syft internally to walk the image).
     * **git/zip/tar**:

       * If an auto-built image exists: scan that (manual export or syft mode), else scan the extracted directory.
   * Output: `scanoss_<label>.json`
4. **Reports**

   * Convert SCANOSS JSON → two Excel files for reviewers.
   * Generate SBOMs (**via Syft in this workflow**) from the same target (image preferred, dir fallback):

     * SPDX JSON, CycloneDX JSON/XML
     * Build `component_layer_map.csv` from Syft JSON (`locations[].layerID`) to show **which container layer** introduced each component/file.
5. **Artifacts**

   * Everything is uploaded as **`oss-scan-results-<LABEL>-<RUN_TAG>`**.
   * `LABEL` comes from the input (image ref, repo name/ref, or filename) and is sanitized.
     `RUN_TAG` is `client_run_id` (if provided) or `GITHUB_RUN_ID`.

**Secrets & permissions**

* Repo → **Settings → Secrets and variables → Actions**

  * `SCANOSS_API_KEY` (**required**) — SCANOSS key for server matching.
  * `SCANOSS_API_URL` (**optional**) — if you use a private SCANOSS endpoint.
* No special GitHub token scopes beyond default are required for running this workflow.

**What you’ll see in the logs**

* Normalization details (repo URL/ref, image ref).
* Whether a Dockerfile was detected & image built.
* SCANOSS JSON size/preview (for quick sanity).
* SBOM generation summary and the layer-map CSV write.

---

## 3) How to use the UI (GitHub Actions “Run workflow”)

1. **Open**: GitHub → **Actions** tab → select **“OSS Compliance - SCANOSS…”** workflow.
2. **Click “Run workflow”** (top-right) and fill the form:

   * **Common**:

     * `client_run_id` – optional; use a human tag like `prod-api_2025-09-14`.
   * **Docker image scan**:

     * `scan_type` = `docker`
     * `docker_image` = e.g. `eclipse-temurin:17-jre-alpine`
     * `image_scan_mode`:

       * `manual` → exports rootfs then scans (good default, works offline)
       * `syft` → SCANOSS uses Syft’s image walker under the hood
   * **Git repo scan**:

     * `scan_type` = `git`
     * `git_url` = repo URL; you can paste a **/tree/<tag>** or **/releases/tag/<tag>** link; the ref is auto-detected
     * `git_ref` = optional (branch/tag/commit). If empty and your URL includes a ref, that wins; otherwise `main`.
   * **Uploaded archive**:

     * `scan_type` = `upload-zip` or `upload-tar`
     * `archive_url` = direct URL to the archive (e.g., release asset or public HTTP/S link)
3. **Run** and wait for the job to finish.
4. **Download artifacts**:

   * In the run page, open **Artifacts** → download **`oss-scan-results-<LABEL>-<RUN_TAG>`**.
   * Inside you’ll find:

     * `scanoss_<LABEL>.json`
     * `<LABEL>_scanoss_components_report.xlsx`
     * `<LABEL>_compliance_merged_report.xlsx`
     * `sbom_<LABEL>.spdx.json`, `sbom_<LABEL>.cdx.json`, `sbom_<LABEL>.cdx.xml` *(from Syft in this workflow)*
     * `syft_image.json` *(raw Syft output for provenance)*
     * `component_layer_map.csv` *(component → layer IDs for images)*

**Tips**

* If you only want SCANOSS and no SBOMs, you can remove or skip the “Generate SBOMs” step later.
* For **layer attribution**, prefer scanning an **image** (docker or auto-built) rather than a plain directory.
* If the SCANOSS JSON is empty or tiny, verify your input path/ref (common cause is pointing at an empty folder or a bad archive URL).

