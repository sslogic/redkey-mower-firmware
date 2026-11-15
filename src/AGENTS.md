# Purpose
- Maintain the offline planner and Wi-Fi uploader as distinct programs.

# Ownership
- planner/ owns geometric rules and synthetic maps; uploader/ owns image validation, cloud OTA transport and local UI.

# Local Contracts
- The planner never commands hardware. The uploader never relabels or patches firmware.
- Keep account and serial fields blank in shipped UI. Use synthetic identifiers only in tests.
- UI binds loopback; firmware serving is limited to the explicitly selected image and LAN interface.
- No OTA retry after ambiguous submission. Keep device progress distinct from command acceptance.
- Credentials remain in memory; no real account access in tests.

# Verification
- `python src/planner/test_planner.py` and `python src/uploader/test_uploader.py` after installing dependencies.

# Child DOX Index
- This document owns both source subdirectories.
