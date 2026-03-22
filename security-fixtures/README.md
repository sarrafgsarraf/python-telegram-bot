## Intentionally vulnerable security fixtures

This directory exists only for **testing CI/CD security tooling**. Nothing here is production code.

### By category

| Category | Files |
|----------|--------|
| **SAST** | `sast_vulnerable.py`, `sast_extra.py`, `ci_fixture_shell.sh` |
| **SCA** | `requirements-sca.txt`, `requirements-vulnerable.txt`, `npm-ci-fixture/package.json` |
| **EOL / legacy deps** | `requirements-eol.txt`, `requirements-vulnerable.txt` |
| **IaC** | `main.tf`, `cloudformation_insecure.yaml`, `insecure_k8s.yaml`, `docker-compose.insecure.yml` |
| **Secrets** | `.env.vulnerable`, `secrets.fake-ci.json` (fake values only) |
| **Container** | `Dockerfile.insecure`, `docker-compose.insecure.yml` |

### Notes

- `requirements-vulnerable.txt` may include pins that **do not install** on very new Python versions; use `requirements-sca.txt` / `requirements-eol.txt` for reliable `pip-audit` runs.
- `npm-ci-fixture/package.json` is for **npm audit** / supply-chain tools if your pipeline scans JavaScript manifests.

Keep this directory isolated from runtime code paths.
