## Intentionally Vulnerable Security Fixtures

This directory exists only for testing CI/CD security tooling.

The files here are intentionally insecure and should never be used in production:

- `sast_vulnerable.py`: examples for SAST findings
- `requirements-vulnerable.txt`: vulnerable and EOL dependencies for SCA/EOL checks
- `main.tf`: insecure IaC patterns for Terraform scanning
- `Dockerfile.insecure`: insecure container configuration
- `.env.vulnerable`: fake credentials for secret-scanning validation

Keep this directory isolated from runtime code paths.
