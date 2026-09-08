#!/usr/bin/env python3
import copy
import hashlib
import json
import os
from pathlib import Path

ROOT = Path("CURRENT_STATE.md")
REQUEST = Path("State/checkpoint_request.json")
RESULT = Path("State/checkpoint_adapter_result.json")
SUMMARY = Path("State/CURRENT_STATE_SUMMARY.json")
CANDIDATES = Path("State/candidates")
EVIDENCE = Path("State/evidence")
EXPECTED_SCHEMA = "serial-light-checkpoint-v1"
EXPECTED_PROJECT = "UseSafeWeb.com"
EXPECTED_GOVERNANCE = "SERIAL_LIGHT"
SHARD_SIZE = 64


def fail(message):
    raise SystemExit(f"CHECKPOINT_ADAPTER_FAIL: {message}")


def canonical_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def git_blob_sha(raw):
    header = f"blob {len(raw)}\0".encode("ascii")
    return hashlib.sha1(header + raw).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical_bytes(value)
    path.write_bytes(raw)
    return raw, git_blob_sha(raw)


def read_json(path):
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        fail(f"missing file: {path}")
    if raw.startswith(b"\xef\xbb\xbf"):
        fail(f"UTF-8 BOM forbidden: {path}")
    if b"\r" in raw:
        fail(f"CR line endings forbidden: {path}")
    if not raw.endswith(b"\n"):
        fail(f"final newline required: {path}")
    try:
        text = raw.decode("utf-8")
        value = json.loads(text)
    except Exception as exc:
        fail(f"invalid UTF-8/JSON in {path}: {exc}")
    if canonical_bytes(value) != raw:
        fail(f"non-canonical JSON serialization: {path}")
    return value, raw


def require(condition, message):
    if not condition:
        fail(message)


def validate_checkpoint(cp, expected_revision=None, expected_baseline=None):
    require(isinstance(cp, dict), "checkpoint must be an object")
    require(cp.get("checkpoint_schema") == EXPECTED_SCHEMA, "checkpoint schema mismatch")
    require(cp.get("project_id") == EXPECTED_PROJECT, "project identity mismatch")
    require(cp.get("governance_mode") == EXPECTED_GOVERNANCE, "governance mode mismatch")
    require(isinstance(cp.get("checkpoint_revision"), int), "checkpoint revision missing")
    if expected_revision is not None:
        require(cp["checkpoint_revision"] == expected_revision, "checkpoint revision mismatch")

    baseline = cp.get("baseline")
    runtime = cp.get("runtime")
    require(isinstance(baseline, dict) and isinstance(runtime, dict), "baseline/runtime missing")
    require(isinstance(baseline.get("version"), int) and baseline["version"] >= 1, "invalid baseline version")
    if expected_baseline is not None:
        require(baseline["version"] == expected_baseline, "baseline version mismatch")

    work = baseline.get("work_items")
    items = runtime.get("items")
    require(isinstance(work, list) and work, "baseline work_items missing")
    require(isinstance(items, list) and items, "runtime items missing")

    work_by_id = {}
    order_by_id = {}
    ac_by_id = {}
    orders = set()
    for wi in work:
        wid = wi.get("id")
        order = wi.get("order")
        require(isinstance(wid, str) and wid, "invalid work item id")
        require(wid not in work_by_id, f"duplicate work item id: {wid}")
        require(isinstance(order, int) and order > 0 and order not in orders, f"invalid/duplicate order: {wid}")
        path = wi.get("wbs_path")
        require(isinstance(path, list) and path and path[-1] == wid, f"invalid wbs_path: {wid}")
        deps = wi.get("depends_on")
        gates = wi.get("gates")
        acs = wi.get("acceptance_criteria")
        require(isinstance(deps, list) and len(deps) == len(set(deps)), f"invalid dependencies: {wid}")
        require(wid not in deps, f"self dependency: {wid}")
        require(isinstance(gates, list) and len(gates) == len(set(gates)), f"invalid gates: {wid}")
        require(isinstance(acs, list) and acs, f"acceptance criteria missing: {wid}")
        ac_ids = [ac.get("id") for ac in acs]
        require(all(isinstance(x, str) and x for x in ac_ids) and len(ac_ids) == len(set(ac_ids)), f"invalid AC ids: {wid}")
        work_by_id[wid] = wi
        order_by_id[wid] = order
        ac_by_id[wid] = set(ac_ids)
        orders.add(order)

    for wid, wi in work_by_id.items():
        for dep in wi["depends_on"]:
            require(dep in work_by_id, f"missing dependency {dep} for {wid}")

    visiting = set()
    visited = set()
    def visit(wid):
        if wid in visited:
            return
        require(wid not in visiting, f"dependency cycle at {wid}")
        visiting.add(wid)
        for dep in work_by_id[wid]["depends_on"]:
            visit(dep)
        visiting.remove(wid)
        visited.add(wid)
    for wid in work_by_id:
        visit(wid)

    runtime_ids = [it.get("id") for it in items]
    require(len(runtime_ids) == len(set(runtime_ids)), "duplicate runtime item id")
    require(set(runtime_ids) == set(work_by_id), "runtime/baseline IDs are not one-to-one")
    expected_runtime_order = [wi["id"] for wi in sorted(work, key=lambda x: (x["order"], x["id"]))]
    require(runtime_ids == expected_runtime_order, "runtime item order differs from baseline order")

    valid_status = {"TODO", "WAITING", "BLOCKED", "PASS"}
    for it in items:
        wid = it["id"]
        status = it.get("status")
        refs = it.get("acceptance_references")
        require(status in valid_status, f"invalid runtime status: {wid}")
        require(isinstance(refs, list), f"acceptance_references missing: {wid}")
        ref_ac = [ref.get("ac_id") for ref in refs]
        require(len(ref_ac) == len(set(ref_ac)), f"duplicate AC reference: {wid}")
        require(set(ref_ac).issubset(ac_by_id[wid]), f"unknown AC reference: {wid}")
        if status == "PASS":
            require(set(ref_ac) == ac_by_id[wid], f"PASS lacks exact AC proof: {wid}")
            require("wait" not in it and "blocker" not in it and "continuation_note" not in it, f"invalid PASS payload: {wid}")
        elif status == "WAITING":
            require(isinstance(it.get("wait"), dict) and "blocker" not in it, f"invalid WAITING payload: {wid}")
        elif status == "BLOCKED":
            require(isinstance(it.get("blocker"), dict) and "wait" not in it, f"invalid BLOCKED payload: {wid}")
        else:
            require("wait" not in it and "blocker" not in it, f"invalid TODO payload: {wid}")

    gate_ids = {g.get("id") for g in baseline.get("gates", [])}
    require(None not in gate_ids, "invalid baseline gate")
    for wi in work:
        require(set(wi.get("gates", [])).issubset(gate_ids), f"unknown work-item gate: {wi['id']}")
    seen_gates = set()
    for gs in runtime.get("gate_satisfactions", []):
        gid = gs.get("gate_id")
        require(gid in gate_ids and gid not in seen_gates, f"invalid gate satisfaction: {gid}")
        seen_gates.add(gid)

    seen_constraints = set()
    for hc in runtime.get("human_constraints", []):
        hid = hc.get("id")
        require(isinstance(hid, str) and hid and hid not in seen_constraints, "invalid human constraint id")
        seen_constraints.add(hid)
        scope = hc.get("scope")
        scoped = hc.get("work_item_ids", [])
        if scope == "PROJECT":
            require(not scoped, f"PROJECT constraint has work items: {hid}")
        elif scope == "WORK_ITEMS":
            require(scoped and len(scoped) == len(set(scoped)) and set(scoped).issubset(work_by_id), f"invalid WORK_ITEMS constraint: {hid}")
        else:
            fail(f"invalid human constraint scope: {hid}")

    closure_ids = {c.get("id") for c in baseline.get("closure_criteria", [])}
    seen_closure = set()
    for cr in runtime.get("closure_references", []):
        cid = cr.get("closure_id")
        require(cid in closure_ids and cid not in seen_closure, f"invalid closure reference: {cid}")
        seen_closure.add(cid)
    if runtime.get("project_status") == "DONE":
        require(runtime.get("governance_blocker") is None, "DONE with governance blocker")
        statuses = {it["id"]: it["status"] for it in items}
        for wi in work:
            if wi.get("required_for_completion"):
                require(statuses[wi["id"]] == "PASS", f"DONE with incomplete required item: {wi['id']}")
        require(seen_closure == closure_ids, "DONE without complete closure proof")

    return {
        "work_items": len(work),
        "status_counts": {s: sum(1 for it in items if it["status"] == s) for s in sorted(valid_status)},
    }


def assert_semantically_equivalent(source, candidate):
    require(source["checkpoint_schema"] == candidate["checkpoint_schema"], "candidate schema changed")
    require(source["project_id"] == candidate["project_id"], "candidate project changed")
    require(source["governance_mode"] == candidate["governance_mode"], "candidate governance changed")
    require(source["checkpoint_revision"] == candidate["checkpoint_revision"], "candidate revision changed")
    require(source["baseline"] == candidate["baseline"], "candidate baseline changed")
    for key in ("project_status", "governance_blocker", "gate_satisfactions", "human_constraints", "closure_references"):
        require(source["runtime"].get(key) == candidate["runtime"].get(key), f"candidate runtime.{key} changed")
    s_items = source["runtime"]["items"]
    c_items = candidate["runtime"]["items"]
    require(len(s_items) == len(c_items), "candidate runtime item count changed")
    for src, cand in zip(s_items, c_items):
        s_copy = copy.deepcopy(src)
        c_copy = copy.deepcopy(cand)
        s_refs = s_copy.pop("acceptance_references")
        c_refs = c_copy.pop("acceptance_references")
        require(s_copy == c_copy, f"candidate runtime semantics changed: {src['id']}")
        require([r["ac_id"] for r in s_refs] == [r["ac_id"] for r in c_refs], f"candidate AC proof coverage changed: {src['id']}")


def load_request():
    request, _ = read_json(REQUEST)
    require(request.get("request_schema") == "usesafeweb-checkpoint-storage-request-v1", "request schema mismatch")
    require(request.get("operation") in {"build_compaction_candidate", "promote_compaction", "apply_tsk0243_pass"}, "unsupported operation")
    require(isinstance(request.get("expected_checkpoint_blob"), str), "expected checkpoint blob missing")
    require(isinstance(request.get("expected_revision"), int), "expected revision missing")
    require(isinstance(request.get("expected_baseline"), int), "expected baseline missing")
    return request


def load_authority(request):
    cp, raw = read_json(ROOT)
    actual_blob = git_blob_sha(raw)
    require(actual_blob == request["expected_checkpoint_blob"], f"stale checkpoint blob: expected {request['expected_checkpoint_blob']} got {actual_blob}")
    stats = validate_checkpoint(cp, request["expected_revision"], request["expected_baseline"])
    return cp, raw, actual_blob, stats


def evidence_shard_path(revision, lo, hi):
    return Path(f"State/evidence/rev{revision}/ACCEPTANCE_EVIDENCE_{lo:04d}_{hi:04d}.json")


def build_compaction_candidate(request, source, source_raw, source_blob, stats):
    revision = source["checkpoint_revision"]
    work_by_id = {wi["id"]: wi for wi in source["baseline"]["work_items"]}
    max_order = max(wi["order"] for wi in work_by_id.values())
    grouped = {}
    for item in source["runtime"]["items"]:
        if not item["acceptance_references"]:
            continue
        order = work_by_id[item["id"]]["order"]
        lo = ((order - 1) // SHARD_SIZE) * SHARD_SIZE + 1
        hi = min(lo + SHARD_SIZE - 1, max_order)
        grouped.setdefault((lo, hi), []).append({
            "id": item["id"],
            "order": order,
            "acceptance_references": copy.deepcopy(item["acceptance_references"]),
        })

    shard_meta = []
    shard_lookup = {}
    for (lo, hi), entries in sorted(grouped.items()):
        shard = {
            "archive_schema": "usesafeweb-checkpoint-acceptance-evidence-v1",
            "authoritative": False,
            "source_checkpoint": {
                "path": "CURRENT_STATE.md",
                "git_blob": source_blob,
                "checkpoint_revision": revision,
                "baseline_version": source["baseline"]["version"],
            },
            "order_range": {"first": lo, "last": hi},
            "items": entries,
        }
        path = evidence_shard_path(revision, lo, hi)
        shard_raw, shard_blob = write_json(path, shard)
        shard_meta.append({
            "path": str(path),
            "git_blob": shard_blob,
            "bytes": len(shard_raw),
            "items_with_evidence": len(entries),
        })
        for entry in entries:
            for ref in entry["acceptance_references"]:
                shard_lookup[(entry["id"], ref["ac_id"])] = (str(path), shard_blob, ref)

    candidate = copy.deepcopy(source)
    for item in candidate["runtime"]["items"]:
        compact = []
        for ref in item["acceptance_references"]:
            path, blob, original = shard_lookup[(item["id"], ref["ac_id"])]
            require(original == ref, f"archive mismatch: {item['id']}/{ref['ac_id']}")
            compact.append({
                "ac_id": ref["ac_id"],
                "evidence_type": "GITHUB_BLOB",
                "reference": f"{path}; blob {blob}#{item['id']}/{ref['ac_id']}",
                "summary": "Full acceptance evidence is preserved in the immutable checkpoint evidence shard.",
            })
        item["acceptance_references"] = compact

    validate_checkpoint(candidate, revision, source["baseline"]["version"])
    assert_semantically_equivalent(source, candidate)
    candidate_path = CANDIDATES / f"CURRENT_STATE_COMPACT_REV{revision}.json"
    candidate_raw, candidate_blob = write_json(candidate_path, candidate)

    manifest = {
        "manifest_schema": "usesafeweb-checkpoint-compaction-candidate-v1",
        "authoritative": False,
        "source": {
            "path": "CURRENT_STATE.md",
            "git_blob": source_blob,
            "checkpoint_revision": revision,
            "baseline_version": source["baseline"]["version"],
            "bytes": len(source_raw),
        },
        "candidate": {
            "path": str(candidate_path),
            "git_blob": candidate_blob,
            "checkpoint_revision": revision,
            "baseline_version": source["baseline"]["version"],
            "bytes": len(candidate_raw),
        },
        "evidence_shards": shard_meta,
        "semantic_result": "PASS",
        "scope": "Acceptance-evidence payload storage only; baseline, task states, dependencies, waits/blockers, constraints, gates, and closure state are unchanged.",
    }
    manifest_path = CANDIDATES / f"CURRENT_STATE_COMPACT_REV{revision}.manifest.json"
    _, manifest_blob = write_json(manifest_path, manifest)

    result = {
        "result_schema": "usesafeweb-checkpoint-storage-result-v1",
        "operation": request["operation"],
        "result": "PASS",
        "source_checkpoint_blob": source_blob,
        "source_revision": revision,
        "baseline_version": source["baseline"]["version"],
        "candidate_path": str(candidate_path),
        "candidate_blob": candidate_blob,
        "candidate_manifest": str(manifest_path),
        "candidate_manifest_blob": manifest_blob,
        "source_bytes": len(source_raw),
        "candidate_bytes": len(candidate_raw),
        "bytes_removed": len(source_raw) - len(candidate_raw),
        "shard_count": len(shard_meta),
        "status_counts": stats["status_counts"],
    }
    write_json(RESULT, result)


def load_candidate_for_promotion(request, source):
    revision = source["checkpoint_revision"]
    candidate_path = CANDIDATES / f"CURRENT_STATE_COMPACT_REV{revision}.json"
    manifest_path = CANDIDATES / f"CURRENT_STATE_COMPACT_REV{revision}.manifest.json"
    candidate, candidate_raw = read_json(candidate_path)
    manifest, _ = read_json(manifest_path)
    require(manifest.get("source", {}).get("git_blob") == request["expected_checkpoint_blob"], "candidate source blob mismatch")
    require(manifest.get("candidate", {}).get("git_blob") == git_blob_sha(candidate_raw), "candidate blob mismatch")
    if request.get("expected_candidate_blob"):
        require(git_blob_sha(candidate_raw) == request["expected_candidate_blob"], "requested candidate blob mismatch")
    validate_checkpoint(candidate, revision, source["baseline"]["version"])
    assert_semantically_equivalent(source, candidate)
    return candidate, candidate_raw, manifest


def write_summary(cp, checkpoint_blob, storage_mode):
    status_counts = {s: 0 for s in ("TODO", "WAITING", "BLOCKED", "PASS")}
    nonpass = []
    for item in cp["runtime"]["items"]:
        status_counts[item["status"]] += 1
        if item["status"] != "PASS":
            nonpass.append({"id": item["id"], "status": item["status"]})
    summary = {
        "summary_schema": "usesafeweb-checkpoint-summary-v1",
        "authoritative": False,
        "authority": {
            "path": "CURRENT_STATE.md",
            "git_blob": checkpoint_blob,
            "checkpoint_revision": cp["checkpoint_revision"],
            "baseline_version": cp["baseline"]["version"],
            "project_id": cp["project_id"],
            "governance_mode": cp["governance_mode"],
            "project_status": cp["runtime"]["project_status"],
        },
        "storage_mode": storage_mode,
        "status_counts": status_counts,
        "nonpass_items": nonpass,
    }
    write_json(SUMMARY, summary)


def promote_compaction(request, source, source_raw, source_blob, stats):
    candidate, _, manifest = load_candidate_for_promotion(request, source)
    require(candidate["checkpoint_revision"] == source["checkpoint_revision"], "candidate revision drift")
    promoted = copy.deepcopy(candidate)
    promoted["checkpoint_revision"] = source["checkpoint_revision"] + 1
    require(promoted["baseline"]["version"] == source["baseline"]["version"], "baseline changed during storage promotion")
    validate_checkpoint(promoted, source["checkpoint_revision"] + 1, source["baseline"]["version"])
    promoted_raw = canonical_bytes(promoted)
    promoted_blob = git_blob_sha(promoted_raw)
    ROOT.write_bytes(promoted_raw)
    write_summary(promoted, promoted_blob, "externalized-acceptance-evidence-v1")
    result = {
        "result_schema": "usesafeweb-checkpoint-storage-result-v1",
        "operation": request["operation"],
        "result": "PASS",
        "old_checkpoint_blob": source_blob,
        "old_revision": source["checkpoint_revision"],
        "new_checkpoint_blob": promoted_blob,
        "new_revision": promoted["checkpoint_revision"],
        "baseline_version": promoted["baseline"]["version"],
        "candidate_manifest": str(CANDIDATES / f"CURRENT_STATE_COMPACT_REV{source['checkpoint_revision']}.manifest.json"),
        "evidence_shards": len(manifest.get("evidence_shards", [])),
        "old_bytes": len(source_raw),
        "new_bytes": len(promoted_raw),
        "status_counts": stats["status_counts"],
        "semantic_result": "PASS",
    }
    write_json(RESULT, result)


def apply_tsk0243_pass(request, source, source_raw, source_blob, stats):
    target = None
    work = None
    for wi in source["baseline"]["work_items"]:
        if wi["id"] == "TSK-0243":
            work = wi
            break
    for item in source["runtime"]["items"]:
        if item["id"] == "TSK-0243":
            target = item
            break
    require(work is not None and target is not None, "TSK-0243 missing")
    require(target["status"] == "WAITING", "TSK-0243 is not WAITING")
    require({ac["id"] for ac in work["acceptance_criteria"]} == {"ACC-0243"}, "unexpected TSK-0243 AC set")

    updated = copy.deepcopy(source)
    for item in updated["runtime"]["items"]:
        if item["id"] == "TSK-0243":
            item["status"] = "PASS"
            item.pop("wait", None)
            item.pop("blocker", None)
            item.pop("continuation_note", None)
            item["acceptance_references"] = [{
                "ac_id": "ACC-0243",
                "evidence_type": "GITHUB_BLOB",
                "reference": "TSK_0243_DNS_VERIFICATION_EVIDENCE_2026-09-08.md; blob a204a2f2aa4ea8463a539c740e58aa72f31ef9d6; commit 3ab5137f7b7a67a47a670223b7adb7a7cb2ddf7d; deployment run/job 34262711990/102184395502; release efe9d4d885d6057b18c5fddea5a0dd2d49d3ec25",
                "summary": "ACC-0243 passed: deterministic signed DNS verification, privacy-safe approved event data, bounded failure/conflict handling, Protection Map mapping, and regression checks are durably evidenced.",
                "verification_context": "Frozen WBS commit 20e2763c0be2124378e3158ac559aed826bc6765, WBS blob 357c5e1be3b455e7efddd329d6a2468e3125b502, corrected evidence blob a204a2f2aa4ea8463a539c740e58aa72f31ef9d6, and production verifier proof 34262711990/102184395502.",
            }]
            break
    updated["checkpoint_revision"] = source["checkpoint_revision"] + 1
    require(updated["baseline"]["version"] == source["baseline"]["version"], "baseline changed during TSK-0243 mutation")
    new_stats = validate_checkpoint(updated, source["checkpoint_revision"] + 1, source["baseline"]["version"])
    updated_raw = canonical_bytes(updated)
    updated_blob = git_blob_sha(updated_raw)
    ROOT.write_bytes(updated_raw)
    write_summary(updated, updated_blob, "externalized-acceptance-evidence-v1")
    result = {
        "result_schema": "usesafeweb-checkpoint-storage-result-v1",
        "operation": request["operation"],
        "result": "PASS",
        "old_checkpoint_blob": source_blob,
        "old_revision": source["checkpoint_revision"],
        "new_checkpoint_blob": updated_blob,
        "new_revision": updated["checkpoint_revision"],
        "baseline_version": updated["baseline"]["version"],
        "stable_mutation": "TSK-0243 WAITING -> PASS; ACC-0243 receives one corrected durable evidence reference.",
        "old_bytes": len(source_raw),
        "new_bytes": len(updated_raw),
        "status_counts": new_stats["status_counts"],
    }
    write_json(RESULT, result)


def main():
    request = load_request()
    source, source_raw, source_blob, stats = load_authority(request)
    operation = request["operation"]
    if operation == "build_compaction_candidate":
        build_compaction_candidate(request, source, source_raw, source_blob, stats)
    elif operation == "promote_compaction":
        promote_compaction(request, source, source_raw, source_blob, stats)
    elif operation == "apply_tsk0243_pass":
        apply_tsk0243_pass(request, source, source_raw, source_blob, stats)
    else:
        fail("unreachable operation")
    print(f"CHECKPOINT_ADAPTER_PASS operation={operation} source_blob={source_blob} revision={source['checkpoint_revision']} baseline={source['baseline']['version']}")


if __name__ == "__main__":
    main()
