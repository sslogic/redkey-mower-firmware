# Purpose
- Publish Redkey mower firmware research, the original-image provenance and verified download link, and development tools.

# Ownership
- Root owns README.md, release status, provenance, privacy policy, manifests and project-wide checks.
- `src/AGENTS.md` owns planner/uploader source and tests.
- `evidence/AGENTS.md` owns sanitized static evidence.
- `tools/AGENTS.md` owns reproducible inspection and publication checks.

# Local Contracts
- Never include account information, credentials, real device identifiers, private network settings, lawn maps, recorded paths, screenshots or personal filesystem paths.
- Never commit the vendor binary or embedded key material. Provide the vendor link/checksum; local downloads stay Git-ignored and byte-identical (embedded version v0.3.5.6).
- Version 0.3.6.0 is planned custom development. Do not create a fake firmware binary or present prototype Python as flashable ESP32 code.
- Separate static findings, inference, local tests and physical acceptance. No live mower installation is established.
- Preserve complete originals before modifying files; make lasting repairs reproducible.
- Keep documentation links and evidence pointers relative to this repository.

# Verification
- Run planner/uploader tests, tools/check_publication.py, and tools/inspect_firmware.py.
- Review the explicit publication file inventory and all added binary assets.

# Child DOX Index
- `src/AGENTS.md`: executable prototype and uploader.
- `evidence/AGENTS.md`: selected static analysis artifacts.
- `tools/AGENTS.md`: portable inspection and privacy checks.
- Root directly owns firmware/, docs/, examples/, .github/ and top-level records.
