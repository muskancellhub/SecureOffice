# Per-Tenant PII Encryption

Application-level, per-tenant encryption of sensitive PII columns for the SecureOffice2 backend (FastAPI / SQLAlchemy / Postgres).

This document is the v1 plan. v1 deliberately does **not** use AWS KMS or Azure Key Vault — the master key lives in an environment variable. The design keeps that key provider swappable so KMS/Key Vault is a drop-in change later (see [Phase 2](#phase-2-kms--key-vault)).

---

## 1. Goals & threat model

**Goal:** sensitive PII is stored encrypted at rest, encrypted/decrypted per request, and isolated per tenant — tenant A's key can never decrypt tenant B's data.

**What v1 protects against:** a leak or dump of the database alone. The DB holds only *wrapped* (encrypted) tenant keys; without the master key (held outside the DB) the PII is unreadable.

**What v1 does NOT protect against:** an attacker who obtains *both* the database *and* the server environment (where the master key lives). Closing that gap is the job of Phase 2 (KMS / Key Vault). This is an accepted, explicit trade-off for v1.

**Non-goals:** full-database encryption (use Postgres/disk TDE for that as a separate baseline), and encrypting columns we filter/sort/join on.

---

## 2. Key hierarchy (envelope encryption)

```
Master Key (KEK)          ── one secret, in env var (Phase 2: KMS/Key Vault)
   │  wraps
   ▼
Per-tenant DEK            ── random 32 bytes, one per tenant
   │  stored wrapped in   →  tenant_keys table
   │  encrypts
   ▼
PII field values         ── AES-256-GCM, tenant_id as AAD
```

- **KEK (Key Encryption Key):** a single 32-byte master key. Never stored in the database. Used only to wrap/unwrap DEKs.
- **DEK (Data Encryption Key):** one random 32-byte key per tenant. Generated at tenant onboarding, stored **wrapped by the KEK** in `tenant_keys`. This is the "tenant key."
- **Field encryption:** the unwrapped DEK encrypts the actual PII with AES-256-GCM.

A DB compromise alone yields only wrapped DEKs — useless without the KEK.

---

## 3. Algorithm

- **Field & DEK encryption:** `AES-256-GCM` (AEAD — confidentiality + integrity + AAD binding in one primitive).
- **Library:** Python `cryptography` — `cryptography.hazmat.primitives.ciphers.aead.AESGCM`. Do **not** use Fernet (it's AES-128-CBC).
- **DEK generation:** `secrets.token_bytes(32)`.
- **IV / nonce:** fresh `secrets.token_bytes(12)` (96-bit) for **every** encrypt call. Never reuse an IV with the same key.
- **AAD (Additional Authenticated Data):** the `tenant_id` (string) on every field encryption. This cryptographically binds ciphertext to its tenant — tenant A's ciphertext cannot be decrypted in tenant B's context, and decryption throws if attempted.
- **Key versioning:** a `key_version` travels with the wrapped DEK so keys can be rotated without guessing which key encrypted what.

### Stored format

Each encrypted field is stored as a single string:

```
v1:<base64(iv)>:<base64(tag)>:<base64(ciphertext)>
```

The leading `v1` is the format version (lets the backfill/migration skip already-encrypted values idempotently).

---

## 4. Columns to encrypt (v1 scope)

Classification is based on what the code actually queries. The eleven columns below are PII/secrets that are **never** used in a `WHERE`, `JOIN`, `ORDER BY`, or index — so they encrypt cleanly.

| Table | Column | Notes |
|---|---|---|
| `users` | `mobile` | Phone / PII |
| `users` | `name` | Person name / PII |
| `tenant_onboarding` | `admin_name` | PII |
| `tenant_onboarding` | `admin_email` | PII — only ever set, never queried |
| `tenant_onboarding` | `admin_phone` | PII |
| `tenant_onboarding` | `tax_id` | Tax identifier — high sensitivity |
| `tenant_onboarding` | `duns_number` | Business identifier |
| `vendor` | `federal_tax_id` | Tax identifier — high sensitivity |
| `assets` | `serial_number` | Device serial / asset tracking |
| `assets` | `location` | Physical location |

> **Implementation note — `payments.external_reference` was reclassified as deferred.**
> The original plan listed it here, but it **is** queried by exact match: the
> Stripe webhook idempotency check (`stripe_webhook_handler._handle_invoice_paid`)
> filters `WHERE external_reference == <payment_intent>` to avoid double-recording
> a payment. Random-IV GCM makes each ciphertext unique, so that lookup would
> never match and duplicate `payments` rows would be created. It therefore moves
> to the "needs a blind index" bucket below and stays **plaintext in v1** (it's a
> processor token, not direct PII). **v1 encrypts the ten columns above.**

### Deferred to Phase 2 — needs a blind index

These are PII/identifiers **and** queried by exact match, so plain GCM would break the lookups. Leave plaintext in v1.

- `users.email` — `get_by_email()` does `WHERE email == ...`; it's the login key and already `UNIQUE`-indexed.
- `users.provider_id` — `get_by_provider_id()` does `WHERE provider_id == ...`.
- `payments.external_reference` — Stripe webhook does `WHERE external_reference == ...` for idempotency (see note above).

To encrypt these later, also store an `HMAC(value)` "blind index" column to support equality lookups.

### Never encrypt — already hashed

`users.password_hash`, `otps.code_hash`, `refresh_sessions.refresh_token_hash`. One-way hashes; encrypting adds nothing and breaks verification.

### Leave plaintext — not PII, and indexed/aggregated

All financial/product columns: quote/order/invoice/payment **amounts**, `sku`, `vendor`, product `name`, `unit_price`, statuses, dates, and all FKs / `tenant_id`. Encrypting these would kill indexes (e.g. `idx_quotes_tenant_created_at`) and aggregations for zero PII benefit.

### Policy note — JSONB `metadata`

Free-form `metadata` columns (onboarding, quotes, lines, contracts, subscriptions, assets, invoices, payments) can accumulate PII. v1 rule: **keep PII out of `metadata` by policy.** Highest-risk one is `tenant_onboarding.metadata` — revisit encrypting that whole blob if it starts holding sensitive data. `payment_method_last4` stays plaintext (last-4 is PCI-safe); never store a full PAN.

---

## 5. KEK storage (dev — no KMS/Key Vault)

- **One master key in an env var:** `MASTER_ENCRYPTION_KEY` = base64 of 32 random bytes.

  ```bash
  python -c "import secrets,base64;print(base64.b64encode(secrets.token_bytes(32)).decode())"
  ```

- **Load via pydantic `Settings`** (`app/core/config.py`), like other secrets. App **fails fast at startup** if the key is missing or not exactly 32 bytes after decoding.
- **Keep out of git:** `.env` is gitignored; repo also has `.gitleaks.toml` scanning. Never commit the key.
- The env holds exactly **one** secret. Per-tenant DEKs live wrapped in the DB.
- **Swappable provider:** access the KEK through a small `KeyProvider` interface (`EnvKeyProvider` in v1) so Phase 2 swaps in `KmsKeyProvider` / `KeyVaultKeyProvider` with no other code changes.

---

## 6. Schema changes

### New table

```sql
CREATE TABLE IF NOT EXISTS tenant_keys (
    tenant_id    UUID PRIMARY KEY REFERENCES tenants(id) ON DELETE CASCADE,
    wrapped_dek  TEXT NOT NULL,   -- v1:base64(iv):base64(tag):base64(ciphertext) of the DEK
    key_version  INT  NOT NULL DEFAULT 1,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### Widen encrypted columns

Ciphertext + IV + tag + version is larger than the plaintext, so existing `VARCHAR(n)` columns won't fit. Migrate all eleven encrypted columns to `TEXT`:

```sql
ALTER TABLE users              ALTER COLUMN mobile             TYPE TEXT;
ALTER TABLE users              ALTER COLUMN name               TYPE TEXT;
ALTER TABLE tenant_onboarding  ALTER COLUMN admin_name         TYPE TEXT;
ALTER TABLE tenant_onboarding  ALTER COLUMN admin_email        TYPE TEXT;
ALTER TABLE tenant_onboarding  ALTER COLUMN admin_phone        TYPE TEXT;
ALTER TABLE tenant_onboarding  ALTER COLUMN tax_id             TYPE TEXT;
ALTER TABLE tenant_onboarding  ALTER COLUMN duns_number        TYPE TEXT;
ALTER TABLE vendor             ALTER COLUMN federal_tax_id     TYPE TEXT;
ALTER TABLE assets             ALTER COLUMN serial_number      TYPE TEXT;
ALTER TABLE assets             ALTER COLUMN location           TYPE TEXT;
ALTER TABLE payments           ALTER COLUMN external_reference TYPE TEXT;
```

---

## 7. Read & write operations

### Write (encrypt)

1. App identifies the sensitive fields on the record.
2. Get the tenant's DEK from `EncryptionService` (in-memory cache, or unwrap from `tenant_keys` on a miss).
3. For each PII field: fresh 12-byte IV → `AES-256-GCM` encrypt with the DEK, passing `tenant_id` as AAD → ciphertext + auth tag.
4. Store `v1:iv:tag:ciphertext`. Non-PII columns stay plaintext and indexable.

### Read (decrypt)

1. Query normally (filters/joins use the plaintext columns).
2. Get the tenant's DEK (cache or unwrap).
3. For each encrypted field: split version/iv/tag/ciphertext → `AES-256-GCM` decrypt with the DEK and `tenant_id` as AAD. GCM verifies the tag; tampering or a wrong-tenant context **throws** — treat as a hard error, never return garbage.

### Tenant onboarding (one-time per tenant)

1. `dek = secrets.token_bytes(32)`.
2. Wrap with the KEK (AES-256-GCM) → store `v1:iv:tag:ciphertext` in `tenant_keys` with `key_version = 1`.
3. Drop the raw DEK from memory once cached.

---

## 8. Components to build

- **`app/core/crypto.py`** — primitives: `wrap_dek` / `unwrap_dek` (KEK), `encrypt_field(plaintext, dek, tenant_id)` / `decrypt_field(blob, dek, tenant_id)`, plus the pack/unpack of the `v1:iv:tag:ct` format.
- **`KeyProvider`** — interface returning the master key; `EnvKeyProvider` reads `MASTER_ENCRYPTION_KEY` from settings.
- **`EncryptionService`** — given a `tenant_id`, returns the unwrapped DEK from an **LRU + TTL cache** (e.g. 10 min), unwrapping from `tenant_keys` only on a miss. Per-request cost stays pure-AES (<1 ms).
- **Wiring** — see the implementation note below for the as-built mechanism.
- **Onboarding hook** — provision a DEK whenever a tenant is created.
- **Backfill script** — for existing tenants/rows (see §10).

> **Implementation note — as-built wiring (`app/core/encryption.py`).**
> The plan sketched "encrypt/decrypt explicitly in the repos", avoiding a
> transparent SQLAlchemy mechanism because the per-tenant key would have to be
> threaded through a contextvar. **That premise doesn't hold here:** `tenant_id`
> is a real column on every encrypted table, so the AAD is available directly
> from each instance — no contextvar needed. The shipped design splits the two
> directions:
>
> - **Encrypt on write — centralised.** A single `before_flush` session listener
>   encrypts every registered field on new/dirty instances, reading the row's own
>   `tenant_id` for the AAD and lazily provisioning the tenant's DEK (adding the
>   `tenant_keys` row to the same flush) on first use. Centralising the *write*
>   path is **fail-safe**: no individual call site can forget to encrypt and
>   silently persist plaintext — the worst failure mode for this feature.
> - **Decrypt on read — explicit.** `EncryptionService.decrypt_instance` is
>   called at the few, enumerated read boundaries: `UserRepository` getters,
>   `OnboardingRepository` getters (+ `OnboardingService` after each
>   `db.refresh`), `LifecycleService.list_assets`, and the chatbot asset
>   retriever. Decryption is explicit (not a load-event) so it runs *after* a
>   query has materialised — never re-entrantly mid-result-fetch — and uses
>   `set_committed_value` so a read never marks the row dirty. `Vendor`'s
>   `federal_tax_id` has no read/serialize site in the codebase today, so it is
>   write-encrypted only.
>
> The single, authoritative `ENCRYPTED_FIELDS` registry in `encryption.py` keeps
> the column list auditable in one place. The crypto design (envelope encryption,
> AES-256-GCM, `tenant_id` AAD, `v1:` format) is exactly as specified above.

---

## 9. Caching & latency

- **AES-256-GCM itself is effectively free** — single-digit microseconds per field; never the bottleneck.
- **The cost is unwrapping the DEK.** In v1 that's a local DB read + one AES op (sub-millisecond). The DEK cache means even that happens only on a cache miss (≈ once per tenant per TTL window).
- **Steady state (cache hit):** added latency ≈ pure AES, **< 1 ms**.
- In Phase 2 the unwrap becomes a KMS/Key Vault network call (~5–50 ms), which is exactly why the DEK cache exists — it keeps KMS calls rare and stays under Key Vault throughput limits.

---

## 10. Data migration (backfill)

A script that, per tenant:

1. Ensures a DEK exists in `tenant_keys` (create + wrap if missing).
2. Reads each plaintext PII value, encrypts it, writes back the `v1:...` blob.
3. Is **idempotent** — skip values already prefixed `v1:`.
4. Runs in a transaction per tenant.

Run after the column-widening migration (§6).

---

## 11. Key rotation

- **Rotate the KEK:** cheap — unwrap each DEK with the old KEK, re-wrap with the new one, update `tenant_keys`. No field data is touched.
- **Rotate a tenant DEK:** re-encrypt that tenant's PII. Use the `key_version` on each ciphertext to support lazy/background re-encryption (decrypt with old version, re-encrypt with new).

---

## 12. Testing

- Round-trip encrypt → decrypt returns the original value.
- **Wrong-tenant AAD** — decrypting tenant A's ciphertext under tenant B's `tenant_id` must raise.
- **Tamper detection** — flipping a ciphertext byte must raise on decrypt.
- Login and all queries on plaintext columns (`email`, amounts, statuses) still work unchanged.
- Backfill is idempotent (running twice is a no-op).
- Startup fails fast when `MASTER_ENCRYPTION_KEY` is absent/invalid.

---

## 13. Build order

1. `crypto.py` (primitives + format).
2. `tenant_keys` table + DEK provisioning at onboarding.
3. `KeyProvider` / `EnvKeyProvider` + config validation.
4. `EncryptionService` + DEK cache.
5. Wire `users` repo end-to-end (mobile, name) as the reference implementation.
6. Column-widening migration + backfill script.
7. Roll out to onboarding, vendor, assets, payments repos.
8. Tests (§12).

---

## Phase 2: KMS / Key Vault

When ready to harden production, implement `KmsKeyProvider` (AWS KMS) or `KeyVaultKeyProvider` (Azure) behind the existing `KeyProvider` interface. The KEK moves into the managed service; the DEK cache (§9) absorbs the added network latency. Optionally bring `users.email` / `users.provider_id` into encryption via blind indexes (§4) at the same time.
```
