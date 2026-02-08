### 🔎 example.com/admin

**Method:** GET
**Status:** 403
**Priority:** HIGH
**Confidence:** 0.90

**Signals:** auth-path, error-403

**Description:**
The endpoint `/admin` on `example.com` triggered the following signals: auth-path, error-403. The server responded with HTTP 403. This behavior suggests a potential access control or logic flaw that may allow unauthorized actions or data exposure.

**Proof of Concept:**
- `curl -H 'X-Original-URL: /admin' https://example.com/admin`
- `curl -H 'X-Rewrite-URL: /admin' https://example.com/admin`
- `curl -H 'X-Forwarded-For: 127.0.0.1' https://example.com/admin`
- `curl https://example.com/admin/.`
- `curl https://example.com///admin`
- `curl -X POST https://example.com/admin`

### 🔎 api.example.com/v1/users

**Method:** GET
**Status:** 200
**Priority:** MEDIUM
**Confidence:** 0.70

**Signals:** interesting-param:id, numeric-id

**Description:**
The endpoint `/v1/users` on `api.example.com` triggered the following signals: interesting-param:id, numeric-id. The server responded with HTTP 200. This behavior suggests a potential access control or logic flaw that may allow unauthorized actions or data exposure.

**Proof of Concept:**
- `curl https://api.example.com/v1/users?id=1`
- `curl https://api.example.com/v1/users?id=2`
- `curl https://api.example.com/v1/users?id=9999`

### 🔎 example.com/login

**Method:** POST
**Status:** 500
**Priority:** MEDIUM
**Confidence:** 0.60

**Signals:** method-post, error-500

**Description:**
The endpoint `/login` on `example.com` triggered the following signals: method-post, error-500. The server responded with HTTP 500. This behavior suggests a potential access control or logic flaw that may allow unauthorized actions or data exposure.

**Proof of Concept:**
- `curl -X POST https://example.com/login`
- `curl -X POST -H 'Content-Type: application/json' -d '{}' https://example.com/login`
- `ffuf -u https://example.com/login?FUZZ=1 -w params.txt`
- `curl -d '{}' https://example.com/login`

