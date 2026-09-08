#!/usr/bin/env python3
import copy
from pathlib import Path

import checkpoint_storage_adapter as v1
import checkpoint_storage_adapter_v2 as v2

OPERATION = "apply_website_deployment_sequencing_override"
TARGET_ID = "TSK-0468"
RELEASE_COMMIT = "907d3880026ca73be949cfc7ecee14eff3efb60c"
BYPASSED_DEPENDENCIES = ["TSK-0151", "TSK-0472"]
APPROVAL_PATH = Path("State/evidence/human/WEBSITE_DEPLOYMENT_SEQUENCING_OVERRIDE_2026-09-08.json")
APPROVAL_BLOB = "e500e169d709325ed04aacf978e99357a6af6591"
APPROVAL_REFERENCE = f"{APPROVAL_PATH}; blob {APPROVAL_BLOB}"
POLICY_ID = "POL-016"


def validate_override_request(request):
    v1.require(request.get("request_schema") == "usesafeweb-checkpoint-storage-request-v1", "request schema mismatch")
    v1.require(request.get("operation") == OPERATION, "operation mismatch")
    v1.require(isinstance(request.get("request_id"), str) and request["request_id"], "request id missing")
    v1.require(isinstance(request.get("expected_checkpoint_blob"), str), "expected checkpoint blob missing")
    v1.require(isinstance(request.get("expected_revision"), int), "expected revision missing")
    v1.require(isinstance(request.get("expected_baseline"), int), "expected baseline missing")
    v1.require(request.get("approval_reference") == APPROVAL_REFERENCE, "approval reference mismatch")
    v1.require(request.get("release_commit") == RELEASE_COMMIT, "release commit mismatch")
    v1.require(request.get("bypassed_dependencies") == BYPASSED_DEPENDENCIES, "bypassed dependency set mismatch")


def validate_approval_evidence():
    approval, approval_raw = v1.read_json(APPROVAL_PATH)
    v1.require(v1.git_blob_sha(approval_raw) == APPROVAL_BLOB, "approval evidence blob mismatch")
    v1.require(approval.get("evidence_schema") == "usesafeweb-human-approval-v1", "approval evidence schema mismatch")
    v1.require(approval.get("project_id") == "UseSafeWeb.com", "approval project mismatch")
    v1.require(approval.get("approval_text") == "Approve one-time website deployment sequencing override.", "approval text mismatch")
    scope = approval.get("scope", {})
    v1.require(scope.get("work_item_id") == TARGET_ID, "approval target mismatch")
    v1.require(scope.get("release_commit") == RELEASE_COMMIT, "approval release mismatch")
    v1.require(scope.get("sequencing_dependencies_bypassed") == BYPASSED_DEPENDENCIES, "approval dependency scope mismatch")
    v1.require(scope.get("one_time") is True, "approval is not one-time")


def apply_website_deployment_sequencing_override(request, source, source_raw, source_blob, stats):
    validate_approval_evidence()

    target_work = next((wi for wi in source["baseline"]["work_items"] if wi["id"] == TARGET_ID), None)
    target_runtime = next((item for item in source["runtime"]["items"] if item["id"] == TARGET_ID), None)
    v1.require(target_work is not None and target_runtime is not None, f"{TARGET_ID} missing")
    v1.require(target_work.get("title") == "Deploy production web/application/content release candidate", "target title mismatch")
    v1.require(target_work.get("depends_on") == BYPASSED_DEPENDENCIES, "target dependency baseline drift")
    v1.require(target_runtime.get("status") == "WAITING", "target is not WAITING")
    v1.require(not any(rule.get("id") == POLICY_ID for rule in source["baseline"].get("policy_rules", [])), f"{POLICY_ID} already exists")

    updated = copy.deepcopy(source)
    updated["checkpoint_revision"] = source["checkpoint_revision"] + 1
    updated["baseline"]["version"] = source["baseline"]["version"] + 1
    updated["baseline"]["policy_rules"].append({
        "id": POLICY_ID,
        "text": (
            "Owner-approved one-time website deployment sequencing override for TSK-0468 release "
            f"{RELEASE_COMMIT}: TSK-0151 and TSK-0472 are not hard sequencing dependencies for this release only. "
            "This does not mark those tasks PASS, change their runtime states, waive any TSK-0468 acceptance, "
            "security, health, accessibility or rollback requirement, alter any unrelated task, or authorize "
            f"master-plan repair. Approval proof: {APPROVAL_REFERENCE}."
        ),
    })

    for wi in updated["baseline"]["work_items"]:
        if wi["id"] == TARGET_ID:
            wi["depends_on"] = []
            break

    for item in updated["runtime"]["items"]:
        if item["id"] == TARGET_ID:
            item["wait"] = {
                "condition": (
                    "The owner-approved one-time sequencing override removes TSK-0151 and TSK-0472 as hard "
                    f"sequencing dependencies for TSK-0468 release {RELEASE_COMMIT}. TSK-0468 remains WAITING only "
                    "until a verified production-host execution path is available and the unchanged deployment "
                    "preconditions can be checked."
                ),
                "resolution_check": (
                    "Reload the current checkpoint and approval evidence; verify a production-host execution path "
                    f"for release {RELEASE_COMMIT} is available; confirm no new material safety, security or platform "
                    "blocker exists; and verify the unchanged TSK-0468 deployment, health, smoke, security, "
                    "accessibility and rollback requirements can be executed. Only then transition TSK-0468 from "
                    "WAITING to TODO in one confirmed checkpoint mutation before deployment."
                ),
                "reference": APPROVAL_REFERENCE,
            }
            break

    # Normalize the intended delta back to the source and prove that every other field is byte-semantically unchanged.
    normalized = copy.deepcopy(updated)
    normalized["checkpoint_revision"] = source["checkpoint_revision"]
    normalized["baseline"]["version"] = source["baseline"]["version"]
    v1.require(normalized["baseline"]["policy_rules"][-1]["id"] == POLICY_ID, "override policy ordering mismatch")
    normalized["baseline"]["policy_rules"].pop()
    for wi in normalized["baseline"]["work_items"]:
        if wi["id"] == TARGET_ID:
            wi["depends_on"] = copy.deepcopy(target_work["depends_on"])
            break
    for item in normalized["runtime"]["items"]:
        if item["id"] == TARGET_ID:
            item["wait"] = copy.deepcopy(target_runtime["wait"])
            break
    v1.require(normalized == source, "override attempted an unrelated checkpoint mutation")

    new_stats = v1.validate_checkpoint(
        updated,
        source["checkpoint_revision"] + 1,
        source["baseline"]["version"] + 1,
    )
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
        "old_baseline_version": source["baseline"]["version"],
        "new_baseline_version": updated["baseline"]["version"],
        "target_work_item": TARGET_ID,
        "release_commit": RELEASE_COMMIT,
        "bypassed_dependencies": BYPASSED_DEPENDENCIES,
        "approval_reference": APPROVAL_REFERENCE,
        "stable_mutation": (
            "One-time TSK-0468 sequencing override recorded; TSK-0468 hard dependencies TSK-0151/TSK-0472 "
            "removed for the approved release only; TSK-0468 remains WAITING pending verified production-host "
            "execution readiness; all acceptance criteria and unrelated state remain unchanged."
        ),
        "old_bytes": len(source_raw),
        "new_bytes": len(updated_raw),
        "status_counts": new_stats["status_counts"],
    }
    v1.write_json(v1.RESULT, result)


def main():
    request, _ = v1.read_json(v1.REQUEST)
    if request.get("operation") != OPERATION:
        v2.main()
        return

    validate_override_request(request)
    source, source_raw, source_blob, stats = v1.load_authority(request)
    apply_website_deployment_sequencing_override(request, source, source_raw, source_blob, stats)
    print(
        f"CHECKPOINT_ADAPTER_V3_PASS operation={request['operation']} source_blob={source_blob} "
        f"revision={source['checkpoint_revision']} baseline={source['baseline']['version']}"
    )


if __name__ == "__main__":
    main()
