# Original vendor firmware — download reference only

The binary is deliberately omitted. Publication review found an embedded unencrypted RSA private key in the vendor's publicly served image, so this repository provides a link and checksum instead of redistributing it.

- [Vendor download: 0.3.5.6.release.bin](https://ldrobotota.s3.amazonaws.com/0.3.5.6.release.bin)
- Embedded version: `v0.3.5.6`; server label: `0.3.5`.
- Exact size: **1,972,000 bytes**.
- SHA-256: `370b8e6d29a77764cf685498fc9e855f93ac992e5ebf5ae17292e666c6b67bae`.
- [Container metadata](metadata.json).

From the repository root, `python tools/fetch_original.py` obtains and verifies a local copy. The destination `firmware/original/redkey-v0.3.5.6.bin` is Git-ignored. The script never overwrites a mismatching existing file and does not authenticate to any vendor account.

The downloaded artifact is an application image, not a complete flash backup, and its integrity checks do not prove compatibility with every board revision. The embedded credential's permissions and revocation status were not tested. See the root README for static findings and limitations.
