#!/usr/bin/env python3
import copy
from pathlib import Path

import checkpoint_storage_adapter as v1

WAITS = Path("State/waits")


def load_request_v2():
    request, _ = v1.read_json(v1.REQUEST)
    v1.require(request.get("request_schema") == "usesafeweb-checkpoint-storage-request-v1", "request schema mismatch")
    v1.require(request.get("operation") in {"build_compaction_candidate", "promote_compaction", "apply_tsk0243_pass"}, "unsupported operation")
    v1.require(isinstance(request.get("expected_checkpoint_blob"), str), "expected checkpoint blob missing")
    v1.require(isinstance(request.get("expected_revision"), int), "expected revision missing")
    v1.require(isinstance(request.get("expected_baseline"), int), "expected baseline missing")
    return request


def wait_shard_path(revision, lo, hi):
    return Path(f"State/waits/rev{revision}/WAIT_PAYLOAD_{lo:04d}_{hi:04d}.json")


def assert_aggressive_equivalence(source, candidate, wait_lookup):
    v1.require(source["checkpoint_schema"] == candidate["checkpoint_schema"], "candidate schema changed")
    v1.require(source["project_id"] == candidate["project_id"], "candidate project changed")
    v1.require(source["governance_mode"] == candidate["governance_mode"], "candidate governance changed")
    v1.require(source["checkpoint_revision"] == candidate["checkpoint_revision"], "candidate revision changed")
    v1.require(source["baseline"] == candidate["baseline"], "candidate baseline changed")
    for key in ("project_status", "governance_blocker", "gate_satisfactions", "human_constraints", "closure_references"):
        v1.require(source["runtime"].get(key) == candidate["runtime"].get(key), f"candidate runtime.{key} changed")

    source_items = source["runtime"]["items"]
    candidate_items = candidate["runtime"]["items"]
    v1.require(len(source_items) == len(candidate_items), "candidate runtime item count changed")
    for src, cand in zip(source_items, candidate_items):
        v1.require(src["id"] == cand["id"], "candidate runtime order changed")
        s_copy = copy.deepcopy(src)
        c_copy = copy.deepcopy(cand)
        s_refs = s_copy.pop("acceptance_references")
        c_refs = c_copy.pop("acceptance_references")
        s_wait = s_copy.pop("wait", None)
        c_wait = c_copy.pop("wait", None)
        v1.require(s_copy == c_copy, f"candidate runtime semantics changed: {src['id']}")
        v1.require([r["ac_id"] for r in s_refs] == [r["ac_id"] for r in c_refs], f"candidate AC proof coverage changed: {src['id']}")
        if s_wait is None:
            v1.require(c_wait is None, f"candidate introduced wait: {src['id']}")
        else:
            v1.require(c_wait is not None, f"candidate removed wait: {src['id']}")
            archived = wait_lookup.get(src["id"])
            v1.require(archived is not None and archived["wait"] == s_wait, f"wait archive mismatch: {src['id']}")
            v1.require(c_wait.get("reference") == archived["reference"], f"wait reference mismatch: {src['id']}")


def build_aggressive_candidate(request, source, source_raw, source_blob, stats):
    revision = source["checkpoint_revision"]
    work_by_id = {wi["id"]: wi for wi in source["baseline"]["work_items"]}
    max_order = max(wi["order"] for wi in work_by_id.values())

    # First externalize full acceptance-reference payloads with v1's deterministic sharding.
    v1.build_compaction_candidate(request, source, source_raw, source_blob, stats)
    candidate_path = v1.CANDIDATES / f"CURRENT_STATE_COMPACT_REV{revision}.json"
    candidate, _ = v1.read_json(candidate_path)
    base_manifest_path = v1.CANDIDATES / f"CURRENT_STATE_COMPACT_REV{revision}.manifest.json"
    base_manifest, _ = v1.read_json(base_manifest_path)

    grouped = {}
    for item in source["runtime"]["items"]:
        if item["status"] != "WAITING":
            continue
        order = work_by_id[item["id"]]["order"]
        lo = ((order - 1) // v1.SHARD_SIZE) * v1.SHARD_SIZE + 1
        hi = min(lo + v1.SHARD_SIZE - 1, max_order)
        grouped.setdefault((lo, hi), []).append({
            "id": item["id"],
            "order": order,
            "wait": copy.deepcopy(item["wait"]),
        })

    wait_meta = []
    wait_lookup = {}
    for (lo, hi), entries in sorted(grouped.items()):
        shard = {
            "archive_schema": "usesafeweb-checkpoint-wait-payload-v1",
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
        path = wait_shard_path(revision, lo, hi)
        raw, blob = v1.write_json(path, shard)
        wait_meta.append({
            "path": str(path),
            "git_blob": blob,
            "bytes": len(raw),
            "waiting_items": len(entries),
        })
        for entry in entries:
            wait_lookup[entry["id"]] = {
                "wait": entry["wait"],
                "reference": f"{path}; blob {blob}#{entry['id']}/wait",
            }

    for item in candidate["runtime"]["items"]:
        if item["acceptance_references"]:
            for ref in item["acceptance_references"]:
                ref["summary"] = "Full proof preserved in immutable evidence shard."
        if item["status"] == "WAITING":
            archived = wait_lookup[item["id"]]
            item["wait"] = {
                "condition": "See immutable wait reference for the exact condition.",
                "resolution_check": "Execute the exact stored resolution_check before any state transition.",
                "reference": archived["reference"],
            }

    v1.validate_checkpoint(candidate, revision, source["baseline"]["version"])
    assert_aggressive_equivalence(source, candidate, wait_lookup)
    candidate_raw, candidate_blob = v1.write_json(candidate_path, candidate)

    manifest = {
        "manifest_schema": "usesafeweb-checkpoint-aggressive-compaction-v1",
        "authoritative": False,
        "source": {
            "path": "CURRENT_STATE.md",
            "git_blob": source_blob,
            "checkpoint_revision": revision,
            "baseline_version": source["baseline"]["version"],
            "bytes": len(source_raw),
            "baseline_bytes": len(v1.canonical_bytes(source["baseline"])),
            "runtime_bytes": len(v1.canonical_bytes(source["runtime"])),
        },
        "candidate": {
            "path": str(candidate_path),
            "git_blob": candidate_blob,
            "checkpoint_revision": revision,
            "baseline_version": source["baseline"]["version"],
            "bytes": len(candidate_raw),
            "baseline_bytes": len(v1.canonical_bytes(candidate["baseline"])),
            "runtime_bytes": len(v1.canonical_bytes(candidate["runtime"])),
        },
        "acceptance_evidence_shards": base_manifest.get("evidence_shards", []),
        "wait_payload_shards": wait_meta,
        "semantic_result": "PASS",
        "scope": "Runtime storage representation only. Baseline, task status, dependency, gate, constraint and closure semantics are unchanged; exact evidence and WAITING payloads remain reconstructable from immutable Git blobs.",
    }
    manifest_raw, manifest_blob = v1.write_json(base_manifest_path, manifest)

    result = {
        "result_schema": "usesafeweb-checkpoint-storage-result-v1",
        "operation": request["operation"],
        "result": "PASS",
        "compaction": "aggressive-runtime-v1",
        "source_checkpoint_blob": source_blob,
        "source_revision": revision,
        "baseline_version": source["baseline"]["version"],
        "candidate_path": str(candidate_path),
        "candidate_blob": candidate_blob,
        "candidate_manifest": str(base_manifest_path),
        "candidate_manifest_blob": manifest_blob,
        "source_bytes": len(source_raw),
        "candidate_bytes": len(candidate_raw),
        "bytes_removed": len(source_raw) - len(candidate_raw),
        "source_baseline_bytes": len(v1.canonical_bytes(source["baseline"])),
        "source_runtime_bytes": len(v1.canonical_bytes(source["runtime"])),
        "candidate_runtime_bytes": len(v1.canonical_bytes(candidate["runtime"])),
        "evidence_shard_count": len(base_manifest.get("evidence_shards", [])),
        "wait_shard_count": len(wait_meta),
        "status_counts": stats["status_counts"],
    }
    v1.write_json(v1.RESULT, result)


def load_aggressive_candidate(request, source):
    revision = source["checkpoint_revision"]
    candidate_path = v1.CANDIDATES / f"CURRENT_STATE_COMPACT_REV{revision}.json"
    manifest_path = v1.CANDIDATES / f"CURRENT_STATE_COMPACT_REV{revision}.manifest.json"
    candidate, candidate_raw = v1.read_json(candidate_path)
    manifest, _ = v1.read_json(manifest_path)
    v1.require(manifest.get("manifest_schema") == "usesafeweb-checkpoint-aggressive-compaction-v1", "aggressive candidate manifest missing")
    v1.require(manifest.get("source", {}).get("git_blob") == request["expected_checkpoint_blob"], "candidate source blob mismatch")
    v1.require(manifest.get("candidate", {}).get("git_blob") == v1.git_blob_sha(candidate_raw), "candidate blob mismatch")
    if request.get("expected_candidate_blob"):
        v1.require(v1.git_blob_sha(candidate_raw) == request["expected_candidate_blob"], "requested candidate blob mismatch")

    wait_lookup = {}
    for meta in manifest.get("wait_payload_shards", []):
        path = Path(meta["path"])
        shard, shard_raw = v1.read_json(path)
        v1.require(v1.git_blob_sha(shard_raw) == meta["git_blob"], f"wait shard blob mismatch: {path}")
        for entry in shard["items"]:
            wait_lookup[entry["id"]] = {
                "wait": entry["wait"],
                "reference": f"{path}; blob {meta['git_blob']}#{entry['id']}/wait",
            }

    v1.validate_checkpoint(candidate, revision, source["baseline"]["version"])
    assert_aggressive_equivalence(source, candidate, wait_lookup)
    return candidate, candidate_raw, manifest


def promote_aggressive(request, source, source_raw, source_blob, stats):
    candidate, _, manifest = load_aggressive_candidate(request, source)
    promoted = copy.deepcopy(candidate)
    promoted["checkpoint_revision"] = source["checkpoint_revision"] + 1
    v1.require(promoted["baseline"]["version"] == source["baseline"]["version"], "baseline changed during storage promotion")
    v1.validate_checkpoint(promoted, source["checkpoint_revision"] + 1, source["baseline"]["version"])
    promoted_raw = v1.canonical_bytes(promoted)
    promoted_blob = v1.git_blob_sha(promoted_raw)
    v1.ROOT.write_bytes(promoted_raw)
    v1.write_summary(promoted, promoted_blob, "aggressive-runtime-shards-v1")
    result = {
        "result_schema": "usesafeweb-checkpoint-storage-result-v1",
        "operation": request["operation"],
        "result": "PASS",
        "compaction": "aggressive-runtime-v1",
        "old_checkpoint_blob": source_blob,
        "old_revision": source["checkpoint_revision"],
        "new_checkpoint_blob": promoted_blob,
        "new_revision": promoted["checkpoint_revision"],
        "baseline_version": promoted["baseline"]["version"],
        "old_bytes": len(source_raw),
        "new_bytes": len(promoted_raw),
        "evidence_shards": len(manifest.get("acceptance_evidence_shards", [])),
        "wait_shards": len(manifest.get("wait_payload_shards", [])),
        "status_counts": stats["status_counts"],
        "semantic_result": "PASS",
    }
    v1.write_json(v1.RESULT, result)


def main():
    request = load_request_v2()
    source, source_raw, source_blob, stats = v1.load_authority(request)
    if request["operation"] == "build_compaction_candidate":
        build_aggressive_candidate(request, source, source_raw, source_blob, stats)
    elif request["operation"] == "promote_compaction":
        promote_aggressive(request, source, source_raw, source_blob, stats)
    elif request["operation"] == "apply_tsk0243_pass":
        v1.apply_tsk0243_pass(request, source, source_raw, source_blob, stats)
    else:
        v1.fail("unreachable operation")
    print(f"CHECKPOINT_ADAPTER_V2_PASS operation={request['operation']} source_blob={source_blob} revision={source['checkpoint_revision']} baseline={source['baseline']['version']}")


if __name__ == "__main__":
    main()
