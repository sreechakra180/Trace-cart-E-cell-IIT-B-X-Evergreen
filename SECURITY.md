# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

If you discover a potential security vulnerability in TraceCart, please do not report it publicly via GitHub Issues. Instead, report it privately to the maintainers.

Please include:
1. Description of the vulnerability and attack vector
2. Steps to reproduce or proof-of-concept payload
3. Potential impact on store edge devices or transaction integrity

We aim to acknowledge reports within 48 hours and provide a fix or mitigation timeline.

## Zero-Biometrics Guarantee

TraceCart is designed to be privacy-preserving by construction:
- **No Face Recognition**: Optical cameras track anonymized bounding box centroids in configured shelf/cart zones only.
- **No Biometric Embeddings**: No persistent biometric identity vectors are stored or transmitted.
- **Path Sanitization**: All endpoints accepting identifiers (`run_id`, `scenario_id`) are strictly whitelisted against regex patterns to prevent filesystem traversal.
- **Upload Validation**: All video uploads are strictly capped at 50 MB, checked for genuine `.mp4` container magic bytes (`ftyp`), and stored with sanitized filenames.
