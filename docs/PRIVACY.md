# Publication privacy and provenance

This public tree is an explicit export of selected files. It is not a copy of the investigation workspace or its backups.

## Owner information excluded

- Account usernames, email addresses, passwords, access tokens and temporary cloud credentials.
- Real mower serials, tablet identifiers, MAC addresses, pairing codes and debugging ports.
- Private LAN addresses, Wi-Fi settings and personal machine/installation paths.
- Real lawn maps, boundary coordinates, recorded travel, mowing history and derived private-lawn measurements.
- Device screenshots, supplied lawn sketches, browser captures, raw logs and signed object-storage URLs.
- Private notes, Obsidian records, backup directories, repair snapshots and local Git configuration.

The public uploader starts with empty account/serial/country fields. Synthetic fixtures use invented identifiers and networks. Loopback addresses are local service defaults, not owner network configuration. Generic API parameter names are protocol documentation, not credential values.

Only a synthetic route diagram is included. The original Android packages, complete decompiled trees and third-party package assets are omitted. Selected bytecode excerpts and derived evidence identify the basis of the technical conclusions.

## Original firmware is linked, not redistributed

The original binary is omitted because it contains credential material. Only a verified vendor download link, checksum, metadata and safe classifications are included. The optional local download is Git-ignored. Its SHA-256 is fixed and verified. It is a downloaded application, not a complete flash dump or NVS export. An unauthenticated request to the public vendor release returned identical bytes without account selection.

**The original vendor image is not credential-free.** It includes a complete RSA private key and matching certificate. This was discovered during publication review and documented in the README and [safe provenance report](../evidence/firmware/public-vendor-provenance.json). No standalone key file, certificate identity values, or authentication probes using the key are provided. Its current privileges and revocation status are unknown.

No vendor private-key bytes are published here. Removing owner data would not remove material already compiled into the generic vendor image, so the binary itself is excluded. Replacing embedded bytes would alter the original image and its integrity values. No such redacted file is misrepresented as original firmware here.

## Checks and limits

The preparation process checked every exported file, including binary bytes, for known owner-specific values in UTF-8 and UTF-16 encodings. Those private comparison values are not embedded in this repository's checker. A separate structural check looks for personal paths, real-looking access keys/JWTs, signed URLs, unexpected capture types and prefilled device serials.

The structural check rejects a tracked vendor binary and private-key material in public files. It allows an untracked, Git-ignored local download for inspection and tests, with a separate checksum check. Passing owner-marker checks is not a universal proof that no unknown, encrypted or proprietary secret representation exists.

All newly published commits use generic project attribution. Existing repository history needs separate review because file sanitization does not change old author metadata. Prior GitHub objects or cached copies may remain outside the current branch history even after a history correction.
