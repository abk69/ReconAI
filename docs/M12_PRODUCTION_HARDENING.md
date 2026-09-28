# M12.3 Response and log hygiene

ReconAI v1.0 stays a single-operator portfolio and demo system. This milestone does not add authentication, workers, or new business behavior. It limits what the API returns and what operational logs record.

## Request correlation

Every HTTP response includes `X-Request-ID`.

- A client may send `X-Request-ID`. The value is echoed when it is 1–128 characters and matches `^[A-Za-z0-9][A-Za-z0-9._-]*$`.
- Any other value, including an empty, oversized, or malformed id, is discarded. The server generates a new UUID.
- The same id is written on the access log for that request.
- The id is a correlation token for operators. It is not an authentication credential and it is not stored as business evidence.

`GET /health` and `GET /ready` keep their existing JSON bodies and also return the header. `/health` is liveness. `/ready` is database readiness.

## Public document responses

`POST /documents`, `GET /documents`, and `GET /documents/{id}` do not include `storage_path`. The column remains in the database. Local file storage and internal services still use it. The dashboard does not read the physical path.

## Errors

Domain responses stay as they are: 400, 404, 409, 422, 429, and 503 still carry their existing safe `detail` text.

An unexpected exception returns HTTP 500:

```json
{"detail": "Internal server error", "request_id": "..."}
```

That body does not include the exception message, a traceback, a database URL, a filesystem path, or a provider payload. The matching server log is `application_error` plus the request id.

## Logging

Access logs record method, path, status, duration, and request id. The path does not include the query string.

Logs do not include API keys, `Authorization` headers, cookies, `DATABASE_URL`, passwords, document contents, OCR text, vendor or policy text, Gemini prompts, Gemini responses, or uploaded bytes. Provider failures log a stable category such as `TIMEOUT`, plus the request id. Gemini success logs may include the model name and token counts.
