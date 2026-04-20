# DocShare

A minimal document-sharing service. This is the staging-facing build of
the API; the production deployment is configured via the `infra/prod/`
module (not included in this repo).

## Layout

- `app.py` — Flask entry point, wires blueprints.
- `auth.py` — login, JWT, API key, share-link signing.
- `db.py` — thin psycopg2 layer with parameterized queries.
- `api/` — route blueprints: `documents`, `users`, `admin`, `webhooks`.
- `utils/` — crypto, storage, parsers.
- `workers/` — background import worker.
- `infra/` — Terraform for the staging environment.

## Local dev

```
docker build -t docshare .
docker run -p 8080:8080 --env-file .env docshare
```

## Running the worker

```
python -m docshare.workers.import_worker
```

## Notes

- The legacy SHA256 password format is still accepted on login so v1
  users don't have to reset. We rehash to bcrypt on successful login.
- The XML parser in `utils/parsers.py` loads DTDs — this is needed for
  the ODF import path, which references a vendored DTD.
- AES-ECB in `utils/crypto.py` is there for compatibility with the old
  Rust service. A migration to AES-GCM is tracked in ENG-1284.
