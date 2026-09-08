# TSK-0243 DNS Verification Evidence — 2026-09-08

## Authority and target

- Task: `TSK-0243` — Implement privacy-safe DNS protection verification.
- Frozen contract: `Plans/Master/WBS/master-wbs.csv@20e2763c0be2124378e3158ac559aed826bc6765`, WBS blob `357c5e1be3b455e7efddd329d6a2468e3125b502`, `ACC-0243` / `VER-0243` / `EVD-0243`.
- Deployed application release: `efe9d4d885d6057b18c5fddea5a0dd2d49d3ec25`.
- Verifier edge: `52.157.109.120` (`adguardvm`). Main web host: `20.71.90.212`.
- Verification date: 2026-09-08.

## Production trust-boundary fix

- Cloudflare DNS-01 capability was confirmed through the owner-provided `CLOUDFLARE_API_TOKEN` GitHub secret without exposing its value.
- Certbot Cloudflare DNS plugin installed on the verifier edge.
- Certificate `verify.usesafeweb.com` issued for `verify.usesafeweb.com` and `*.verify.usesafeweb.com`; direct hostname verification passed; renewal uses a root-only `0600` credential file and Certbot renewal dry-run passed.
- Main web Nginx vhost was minimally extended to accept `*.verify.usesafeweb.com` while preserving the original challenge `Host` into Next.js. Reversible proof changed the challenge request from `404` to `403` while the normal verifier route stayed `403` and the website stayed `200`, then restored the original config before permanent application.
- Permanent main-web result: `DEPLOYMENT=PASS;CHALLENGE_HOST=403;NORMAL_HOST=403;WEB_FINAL=200`; rollback backup: `/var/backups/usesafeweb/node_usesafeweb.conf.pre-verifier-alias.bak`.
- Verifier-edge deployment commit `b1ad9a361cf22f6ff930217a4c8e4bcb78b349fc`; GitHub Actions run `34262711990`, job `102184395502`; final evidence: `DEPLOYMENT=PASS;TLS=PASS;LOCAL_PROBE=403;DOH=400;WEB_FINAL=200;API=405`; rollback backup: `/var/backups/usesafeweb/nginx.conf.pre-verifier-vhost.bak`.
- Edge routing is limited to `/api/dns-verification/probes`, preserves the challenge `Host`, verifies upstream TLS with SNI `usesafeweb.com`, returns `404` for unrelated paths, and leaves the existing `dns.usesafeweb.com` vhost unchanged.

## Exact public WAITING-boundary proof

Historical deterministic challenge: `000000000000000000000000075bcd15.verify.usesafeweb.com`.

Fresh public checks after deployment:

- trusted TLS/SNI and hostname verification: PASS;
- A record: `52.157.109.120`;
- intentionally invalid POST to `/api/dns-verification/probes`: HTTP `403`, proving the approved probe interface is reachable;
- main website after redirect: HTTP `200`;
- requests/results unsupported GET: HTTP `405` / `405`;
- empty DoH request: HTTP `400`.

This satisfies the previously recorded verifier TLS/SNI + probe-interface reachability condition while preserving public application/API and DoH health.

## Functional target proof

A fresh synthetic production journey exercised the signed protocol end to end:

1. POST `/api/dns-verification/requests` returned `201`, a 32-hex challenge, matching wildcard probe host, future expiry, signed request token, exact approved response keys, and `Cache-Control: no-store`.
2. POST of the valid request token to the generated challenge host returned `200`, an observation token, the allowed `https://usesafeweb.com` CORS origin, exact approved response shape, and `no-store`.
3. POST `/api/dns-verification/results` with valid request + observation tokens returned `200` and exactly `{"dnsPath":"verified-fresh","reasonCode":"TECH_VERIFIED","verifierVersion":"private-rewrite-v1"}`.
4. Replaying the same proof returned `409 PROOF_ALREADY_CONSUMED`.

Acceptance suite result: `FUNCTIONAL_ACCEPTANCE=PASS`.

## Negative, bounds, security and privacy proof

Fresh production checks passed:

- disallowed Origin -> `403 ORIGIN_NOT_ALLOWED`;
- wrong probe media type -> `415 UNSUPPORTED_MEDIA_TYPE`;
- valid token on wrong challenge Host -> `403 PROBE_NOT_AUTHORIZED`;
- invalid observation -> `403 PROOF_NOT_AUTHORIZED`;
- replayed valid proof -> `409 PROOF_ALREADY_CONSUMED`;
- invalid scope -> `400 INVALID_REQUEST`;
- wrong request media type -> `415`;
- oversized request body -> `413`;
- request/probe/result responses use `Cache-Control: no-store`;
- successful result exposes exactly `dnsPath`, `reasonCode`, `verifierVersion`; no scope, challenge, request token, observation token, domain, or query fields are returned;
- deployed replay protection stores a SHA-256 digest of request/observation tokens, prunes expired entries, and caps the in-memory replay map at 4096 entries;
- approved result event shape is exactly `{dnsPath, reasonCode, verifierVersion}` and the deployed result route has no console logging of that event.

## Protection Map mapping proof

Deployed bundle checks passed:

- `verified-fresh` -> check state `working` -> Protection Map `protected/verified` with `TECH_VERIFIED`;
- `verified-stale` -> `VERIFY_STALE`;
- failed path maps to failed;
- uncertain/conflict path -> `EVIDENCE_CONFLICT`;
- unreachable path -> `VERIFY_UNREACHABLE`;
- client requests use `no-store` and a bounded 30-second timeout.

## Regression and rollback proof

Fresh regression health after production changes: website `200`; requests/results unsupported GET `405` / `405`; empty DoH request `400`; Nginx configuration validation passed on both changed hosts.

Rollback behavior was exercised rather than assumed:

- reversible main-web alias proof applied, verified, and restored the candidate change;
- an earlier verifier-edge deployment failed its immediate reload-readiness check and restored the previous Nginx config with `NGINX_ROLLBACK=PASS`;
- a later reversible edge SNI diagnostic reapplied the candidate vhost and restored the original Nginx config with `RESTORE=PASS`;
- permanent changes retain the backups named above.

## Verification-system deviation and disposition

Historical preflight run `33900198638` was rerun after the fix. Attempt 48 produced job `102185075298` but failed before any workflow steps (`steps = null`) and GitHub exposed no job log (`BlobNotFound`); attempt 47 had the same pre-step infrastructure character. These runs provide no product result and are not treated as product failure.

Disposition: the exact historical challenge was independently rechecked publicly, the original WAITING trust-boundary condition passed, and the separately authorized production functional/negative/privacy/rollback suite passed against the deployed target. Repeating an equivalent pre-step-failing workflow without new infrastructure evidence is not justified.

## Acceptance conclusion

`ACC-0243` is satisfied under the current deployed inputs and semantics: the supported verification path is deterministic, the privacy boundary does not expose query history, caches/failures/conflicts and bounded error cases are handled, only approved result/event data is emitted, the supported outcomes map to Protection Map rules, and rollback/regression checks passed.
