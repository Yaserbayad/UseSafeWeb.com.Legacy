#!/usr/bin/env python3
import copy
from pathlib import Path

import checkpoint_storage_adapter as v1
import checkpoint_storage_adapter_v6 as v6

OPERATION = "wait_tsk0395_pr120_promotion_authority"
TARGET_ID = "TSK-0395"
EVIDENCE_PATH = Path("State/evidence/reconciliation/TSK0395_PR120_PROMOTION_WAIT_2026-09-09.json")
EVIDENCE_BLOB = "4db15fb1d05fb64af7ebbf0a548d80d6777be2e0"
EVIDENCE_REFERENCE = f"{EVIDENCE_PATH}; blob {EVIDENCE_BLOB}"
PR_NUMBER = 120
PR_HEAD = "c95829e0d9e6101120327981e0ef65f81ab2964c"
LANDING_RUN = 34322321170
LANDING_JOB = 102371540068
PROMOTION_RUN = 34322321186
PROMOTION_JOB = 102371540467


def validate_request(request):
    v1.require(request.get("request_schema") == "usesafeweb-checkpoint-storage-request-v1", "request schema mismatch")
    v1.require(request.get("operation") == OPERATION, "operation mismatch")
    v1.require(isinstance(request.get("request_id"), str) and request["request_id"], "request id missing")
    v1.require(isinstance(request.get("expected_checkpoint_blob"), str), "expected checkpoint blob missing")
    v1.require(request.get("expected_revision") == 57, "expected revision mismatch")
    v1.require(request.get("expected_baseline") == 2, "expected baseline mismatch")
    v1.require(request.get("evidence_reference") == EVIDENCE_REFERENCE, "wait evidence reference mismatch")
    v1.require(request.get("pr_number") == PR_NUMBER, "PR number mismatch")
    v1.require(request.get("pr_head") == PR_HEAD, "PR head mismatch")
    v1.require(request.get("landing_run_id") == LANDING_RUN, "landing run mismatch")
    v1.require(request.get("landing_job_id") == LANDING_JOB, "landing job mismatch")
    v1.require(request.get("promotion_run_id") == PROMOTION_RUN, "promotion run mismatch")
    v1.require(request.get("promotion_job_id") == PROMOTION_JOB, "promotion job mismatch")


def validate_evidence():
    evidence, raw = v1.read_json(EVIDENCE_PATH)
    v1.require(v1.git_blob_sha(raw) == EVIDENCE_BLOB, "wait evidence blob mismatch")
    v1.require(evidence.get("evidence_schema") == "usesafeweb-work-wait-v1", "wait evidence schema mismatch")
    v1.require(evidence.get("project_id") == "UseSafeWeb.com", "wait evidence project mismatch")
    v1.require(evidence.get("work_item_id") == TARGET_ID, "wait evidence target mismatch")
    source = evidence.get("source", {})
    v1.require(source.get("pull_request") == PR_NUMBER, "wait evidence PR mismatch")
    v1.require(source.get("head_commit") == PR_HEAD, "wait evidence head mismatch")
    accepted = evidence.get("verified_partial_outcome", {}).get("landing_acceptance", {})
    v1.require(accepted.get("result") == "PASS", "landing acceptance not PASS")
    v1.require(accepted.get("run_id") == LANDING_RUN, "landing evidence run mismatch")
    v1.require(accepted.get("job_id") == LANDING_JOB, "landing evidence job mismatch")
    artifact = evidence.get("verified_partial_outcome", {}).get("visual_artifact", {})
    v1.require(artifact.get("artifact_id") == 10092378186, "visual artifact mismatch")
    v1.require(str(artifact.get("review", "")).startswith("PASS:"), "visual review not PASS")
    gate = evidence.get("pending_condition", {}).get("promotion_gate", {})
    v1.require(gate.get("run_id") == PROMOTION_RUN, "promotion evidence run mismatch")
    v1.require(gate.get("job_id") == PROMOTION_JOB, "promotion evidence job mismatch")
    v1.require(gate.get("result") == "FAIL", "promotion evidence is not FAIL")
    v1.require(gate.get("landing_code_failure") is False, "promotion failure incorrectly attributed to landing")
    v1.require(evidence.get("pending_condition", {}).get("type") == "HUMAN_AUTHORITY", "wait condition is not human authority")
    v1.require("PR #120" in evidence.get("pending_condition", {}).get("condition", ""), "wait condition scope mismatch")
    v1.require("transition TSK-0395 from WAITING to TODO" in evidence.get("resolution_check", ""), "resolution check mismatch")
    return evidence


def transition(request, source, source_raw, source_blob, stats):
    evidence = validate_evidence()
    target_work = next((wi for wi in source["baseline"]["work_items"] if wi["id"] == TARGET_ID), None)
    target_runtime = next((item for item in source["runtime"]["items"] if item["id"] == TARGET_ID), None)
    v1.require(target_work is not None and target_runtime is not None, f"{TARGET_ID} missing")
    v1.require(source["runtime"].get("project_status") == "ACTIVE", "project is not ACTIVE")
    v1.require(source["runtime"].get("governance_blocker") is None, "project governance blocker present")
    v1.require(target_work.get("title") == "Implement public landing page and primary first-phone CTA", "target title mismatch")
    v1.require(target_work.get("depends_on") == ["TSK-0322", "TSK-0324"], "target dependency drift")
    v1.require(target_runtime.get("status") == "TODO", "target is not TODO")
    v1.require(target_runtime.get("acceptance_references") == [], "target has unexpected acceptance proof")
    v1.require("wait" not in target_runtime and "blocker" not in target_runtime, "target has unexpected stable-boundary payload")

    updated = copy.deepcopy(source)
    updated["checkpoint_revision"] = source["checkpoint_revision"] + 1
    for item in updated["runtime"]["items"]:
        if item["id"] == TARGET_ID:
            item["status"] = "WAITING"
            item["wait"] = {
                "condition": evidence["pending_condition"]["condition"],
                "resolution_check": evidence["resolution_check"],
                "reference": EVIDENCE_REFERENCE,
            }
            break

    normalized = copy.deepcopy(updated)
    normalized["checkpoint_revision"] = source["checkpoint_revision"]
    for item in normalized["runtime"]["items"]:
        if item["id"] == TARGET_ID:
            item["status"] = target_runtime["status"]
            item.pop("wait", None)
            break
    v1.require(normalized == source, "promotion wait transition attempted unrelated checkpoint mutation")

    new_stats = v1.validate_checkpoint(updated, source["checkpoint_revision"] + 1, source["baseline"]["version"])
    v1.require(new_stats["status_counts"]["TODO"] == stats["status_counts"]["TODO"] - 1, "TODO count did not decrement exactly once")
    v1.require(new_stats["status_counts"]["WAITING"] == stats["status_counts"]["WAITING"] + 1, "WAITING count did not increment exactly once")
    v1.require(new_stats["status_counts"]["PASS"] == stats["status_counts"]["PASS"], "PASS count changed")
    v1.require(new_stats["status_counts"]["BLOCKED"] == stats["status_counts"]["BLOCKED"], "BLOCKED count changed")

    updated_raw = v1.canonical_bytes(updated)
    updated_blob = v1.git_blob_sha(updated_raw)
    v1.ROOT.write_bytes(updated_raw)
    v1.write_summary(updated, updated_blob, "externalized-acceptance-evidence-v1")
    result = {
        "result_schema": "usesafeweb-checkpoint-storage-result-v1",
        "operation": request["operation"],
        "request_id": request["request_id"],
        "result": "PASS",
        "old_checkpoint_blob": source_blob,
        "old_revision": source["checkpoint_revision"],
        "new_checkpoint_blob": updated_blob,
        "new_revision": updated["checkpoint_revision"],
        "baseline_version": updated["baseline"]["version"],
        "target_work_item": TARGET_ID,
        "wait_reference": EVIDENCE_REFERENCE,
        "pr_number": PR_NUMBER,
        "pr_head": PR_HEAD,
        "stable_mutation": "TSK-0395 transitioned from TODO to WAITING after full landing/browser/visual acceptance passed on PR #120 but the unrelated repository-wide TSK-0489 promotion gate remained red and the prior PR #119 bypass did not authorize PR #120; baseline and all unrelated runtime state remain unchanged.",
        "old_bytes": len(source_raw),
        "new_bytes": len(updated_raw),
        "status_counts": new_stats["status_counts"],
    }
    v1.write_json(v1.RESULT, result)


def main():
    request, _ = v1.read_json(v1.REQUEST)
    if request.get("operation") != OPERATION:
        v6.main()
        return
    validate_request(request)
    source, source_raw, source_blob, stats = v1.load_authority(request)
    transition(request, source, source_raw, source_blob, stats)
    print(
        f"CHECKPOINT_ADAPTER_V7_PASS operation={request['operation']} source_blob={source_blob} "
        f"revision={source['checkpoint_revision']} baseline={source['baseline']['version']}"
    )


if __name__ == "__main__":
    main()
