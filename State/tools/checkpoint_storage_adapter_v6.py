#!/usr/bin/env python3
import copy
from pathlib import Path

import checkpoint_storage_adapter as v1
import checkpoint_storage_adapter_v5 as v5

OPERATION = "reopen_tsk0395_insufficient_landing"
TARGET_ID = "TSK-0395"
AC_ID = "ACC-0395"
EVIDENCE_PATH = Path("State/evidence/reconciliation/TSK0395_LANDING_REOPEN_2026-09-09.json")
EVIDENCE_BLOB = "a51ac979496ed1b8521231dba117f9891144a6be"
EVIDENCE_REFERENCE = f"{EVIDENCE_PATH}; blob {EVIDENCE_BLOB}"
EXPECTED_TITLE = "Implement public landing page and primary first-phone CTA"
EXPECTED_DEPENDENCIES = ["TSK-0322", "TSK-0324"]
EXPECTED_CONDITION = "Copy matches approved claims; primary CTA is clear; no DNS-led positioning; privacy/limits/support links are present; responsive/accessibility/performance checks pass."


def validate_request(request):
    v1.require(request.get("request_schema") == "usesafeweb-checkpoint-storage-request-v1", "request schema mismatch")
    v1.require(request.get("operation") == OPERATION, "operation mismatch")
    v1.require(isinstance(request.get("request_id"), str) and request["request_id"], "request id missing")
    v1.require(isinstance(request.get("expected_checkpoint_blob"), str), "expected checkpoint blob missing")
    v1.require(request.get("expected_revision") == 56, "expected revision mismatch")
    v1.require(request.get("expected_baseline") == 2, "expected baseline mismatch")
    v1.require(request.get("evidence_reference") == EVIDENCE_REFERENCE, "reassessment evidence reference mismatch")


def validate_evidence():
    evidence, raw = v1.read_json(EVIDENCE_PATH)
    v1.require(v1.git_blob_sha(raw) == EVIDENCE_BLOB, "reassessment evidence blob mismatch")
    v1.require(evidence.get("evidence_schema") == "usesafeweb-acceptance-reassessment-v1", "reassessment evidence schema mismatch")
    v1.require(evidence.get("project_id") == "UseSafeWeb.com", "reassessment project mismatch")
    v1.require(evidence.get("work_item_id") == TARGET_ID, "reassessment target mismatch")
    v1.require(evidence.get("acceptance_id") == AC_ID, "reassessment acceptance mismatch")
    v1.require(evidence.get("fresh_production_verification", {}).get("result") == "PASS", "fresh production verification missing")
    v1.require(evidence.get("fresh_production_verification", {}).get("release_commit") == "907d3880026ca73be949cfc7ecee14eff3efb60c", "production release mismatch")
    source = evidence.get("source_reassessment", {})
    v1.require(source.get("previous_home_component") == "ContentPage", "previous home component mismatch")
    v1.require(source.get("current_home_component") == "LandingPage", "current home component mismatch")
    frozen = evidence.get("frozen_task_semantics", {})
    v1.require(frozen.get("title") == EXPECTED_TITLE, "frozen task title mismatch")
    v1.require(frozen.get("acceptance_condition") == EXPECTED_CONDITION, "frozen acceptance condition mismatch")
    decision = evidence.get("decision", {})
    v1.require(decision.get("result") == "INVALIDATE_ACCEPTANCE_AND_REOPEN", "reassessment did not require reopen")
    v1.require(decision.get("required_state") == "TODO", "reassessment target state mismatch")
    v1.require(decision.get("required_acceptance_references") == [], "reassessment proof clearing mismatch")


def transition(request, source, source_raw, source_blob, stats):
    validate_evidence()
    work_by_id = {wi["id"]: wi for wi in source["baseline"]["work_items"]}
    runtime_by_id = {item["id"]: item for item in source["runtime"]["items"]}
    target_work = work_by_id.get(TARGET_ID)
    target_runtime = runtime_by_id.get(TARGET_ID)
    v1.require(target_work is not None and target_runtime is not None, f"{TARGET_ID} missing")
    v1.require(source["runtime"].get("project_status") == "ACTIVE", "project is not ACTIVE")
    v1.require(source["runtime"].get("governance_blocker") is None, "project governance blocker present")
    v1.require(target_work.get("title") == EXPECTED_TITLE, "target title mismatch")
    v1.require(target_work.get("depends_on") == EXPECTED_DEPENDENCIES, "target dependency drift")
    v1.require([ac.get("id") for ac in target_work.get("acceptance_criteria", [])] == [AC_ID], "target acceptance id drift")
    v1.require(target_work["acceptance_criteria"][0].get("condition") == EXPECTED_CONDITION, "target acceptance semantics drift")
    v1.require(target_runtime.get("status") == "PASS", "target is not PASS")
    refs = target_runtime.get("acceptance_references", [])
    v1.require(len(refs) == 1 and refs[0].get("ac_id") == AC_ID, "target PASS proof shape mismatch")
    v1.require(runtime_by_id["TSK-0322"].get("status") == "PASS", "TSK-0322 dependency not PASS")
    v1.require(runtime_by_id["TSK-0324"].get("status") == "PASS", "TSK-0324 dependency not PASS")
    v1.require(runtime_by_id["TSK-0468"].get("status") == "PASS", "production deployment PASS unexpectedly absent")
    for constraint in source["runtime"].get("human_constraints", []):
        scoped = constraint.get("scope") == "PROJECT" or TARGET_ID in constraint.get("work_item_ids", [])
        v1.require(not scoped, f"human constraint blocks {TARGET_ID}: {constraint.get('id')}")

    updated = copy.deepcopy(source)
    updated["checkpoint_revision"] = source["checkpoint_revision"] + 1
    for item in updated["runtime"]["items"]:
        if item["id"] == TARGET_ID:
            item["status"] = "TODO"
            item["acceptance_references"] = []
            break

    normalized = copy.deepcopy(updated)
    normalized["checkpoint_revision"] = source["checkpoint_revision"]
    for item in normalized["runtime"]["items"]:
        if item["id"] == TARGET_ID:
            item["status"] = target_runtime["status"]
            item["acceptance_references"] = copy.deepcopy(target_runtime["acceptance_references"])
            break
    v1.require(normalized == source, "landing reopen attempted unrelated checkpoint mutation")

    new_stats = v1.validate_checkpoint(updated, source["checkpoint_revision"] + 1, source["baseline"]["version"])
    v1.require(new_stats["status_counts"]["PASS"] == stats["status_counts"]["PASS"] - 1, "PASS count did not decrement exactly once")
    v1.require(new_stats["status_counts"]["TODO"] == stats["status_counts"]["TODO"] + 1, "TODO count did not increment exactly once")
    v1.require(new_stats["status_counts"]["WAITING"] == stats["status_counts"]["WAITING"], "WAITING count changed")
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
        "reassessment_reference": EVIDENCE_REFERENCE,
        "stable_mutation": "TSK-0395 transitioned from PASS to TODO because fresh owner-facing and source evidence invalidated the prior completion interpretation; its prior acceptance proof was cleared; baseline, dependencies, TSK-0468 deployment PASS, and all unrelated runtime state remain unchanged.",
        "old_bytes": len(source_raw),
        "new_bytes": len(updated_raw),
        "status_counts": new_stats["status_counts"],
    }
    v1.write_json(v1.RESULT, result)


def main():
    request, _ = v1.read_json(v1.REQUEST)
    if request.get("operation") != OPERATION:
        v5.main()
        return
    validate_request(request)
    source, source_raw, source_blob, stats = v1.load_authority(request)
    transition(request, source, source_raw, source_blob, stats)
    print(
        f"CHECKPOINT_ADAPTER_V6_PASS operation={request['operation']} source_blob={source_blob} "
        f"revision={source['checkpoint_revision']} baseline={source['baseline']['version']}"
    )


if __name__ == "__main__":
    main()
