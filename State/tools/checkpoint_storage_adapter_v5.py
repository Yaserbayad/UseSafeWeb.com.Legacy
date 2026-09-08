#!/usr/bin/env python3
import copy
from pathlib import Path

import checkpoint_storage_adapter as v1
import checkpoint_storage_adapter_v4 as v4

OPERATION = "mark_tsk0468_pass_production_deployment"
TARGET_ID = "TSK-0468"
AC_ID = "ACC-0468"
RELEASE_COMMIT = "907d3880026ca73be949cfc7ecee14eff3efb60c"
EVIDENCE_PATH = Path("State/evidence/deployment/TSK0468_PRODUCTION_DEPLOYMENT_2026-09-09.json")
EVIDENCE_BLOB = "64414cb49dc5e2674de0de374bfec9c400666133"
EVIDENCE_REFERENCE = f"{EVIDENCE_PATH}; blob {EVIDENCE_BLOB}"
APPROVAL_REFERENCE = "State/evidence/human/TSK0468_PRODUCTION_DEPLOYMENT_APPROVAL_2026-09-09.json; blob 447830ab6ba19fd6d4bda6901072e770af08f8de"
SEQUENCING_APPROVAL_REFERENCE = "State/evidence/human/WEBSITE_DEPLOYMENT_SEQUENCING_OVERRIDE_2026-09-08.json; blob e500e169d709325ed04aacf978e99357a6af6591"
DEPLOY_RUN_ID = 34288791722
DEPLOY_JOB_ID = 102270432495
VERIFY_RUN_ID = 34289013271
VERIFY_JOB_ID = 102271111149
BROWSER_RUN_ID = 34277106920
BROWSER_JOB_ID = 102232725342
PREVIOUS_RELEASE = "efe9d4d885d6057b18c5fddea5a0dd2d49d3ec25"
DEPLOY_SCRIPT_BLOB = "5cea28abde776cfc43d849c3029b62e9a8ebec56"
ACCEPTANCE_REFERENCE = {
    "ac_id": AC_ID,
    "evidence_type": "GITHUB_BLOB",
    "reference": EVIDENCE_REFERENCE,
    "summary": "Exact production deployment, independent post-deploy verification, browser/accessibility acceptance, owner approval, security and rollback proof for release 907d3880026ca73be949cfc7ecee14eff3efb60c.",
}


def validate_request(request):
    v1.require(request.get("request_schema") == "usesafeweb-checkpoint-storage-request-v1", "request schema mismatch")
    v1.require(request.get("operation") == OPERATION, "operation mismatch")
    v1.require(isinstance(request.get("request_id"), str) and request["request_id"], "request id missing")
    v1.require(isinstance(request.get("expected_checkpoint_blob"), str), "expected checkpoint blob missing")
    v1.require(request.get("expected_revision") == 55, "expected revision mismatch")
    v1.require(request.get("expected_baseline") == 2, "expected baseline mismatch")
    v1.require(request.get("release_commit") == RELEASE_COMMIT, "release commit mismatch")
    v1.require(request.get("evidence_reference") == EVIDENCE_REFERENCE, "production evidence reference mismatch")
    v1.require(request.get("deployment_run_id") == DEPLOY_RUN_ID, "deployment run mismatch")
    v1.require(request.get("deployment_job_id") == DEPLOY_JOB_ID, "deployment job mismatch")
    v1.require(request.get("verification_run_id") == VERIFY_RUN_ID, "verification run mismatch")
    v1.require(request.get("verification_job_id") == VERIFY_JOB_ID, "verification job mismatch")
    v1.require(request.get("browser_run_id") == BROWSER_RUN_ID, "browser run mismatch")
    v1.require(request.get("browser_job_id") == BROWSER_JOB_ID, "browser job mismatch")


def validate_evidence():
    evidence, raw = v1.read_json(EVIDENCE_PATH)
    v1.require(v1.git_blob_sha(raw) == EVIDENCE_BLOB, "production evidence blob mismatch")
    v1.require(evidence.get("evidence_schema") == "usesafeweb-production-deployment-evidence-v1", "production evidence schema mismatch")
    v1.require(evidence.get("project_id") == "UseSafeWeb.com", "production evidence project mismatch")
    v1.require(evidence.get("work_item_id") == TARGET_ID, "production evidence target mismatch")
    v1.require(evidence.get("acceptance_id") == AC_ID, "production acceptance id mismatch")
    v1.require(evidence.get("result") == "PASS", "production evidence did not pass")

    owner = evidence.get("owner_approval", {})
    v1.require(owner.get("reference") == APPROVAL_REFERENCE, "owner approval evidence mismatch")
    v1.require(owner.get("sequencing_override_reference") == SEQUENCING_APPROVAL_REFERENCE, "sequencing approval evidence mismatch")

    release = evidence.get("release", {})
    v1.require(release.get("target_commit") == RELEASE_COMMIT, "deployed release mismatch")
    v1.require(release.get("previous_commit") == PREVIOUS_RELEASE, "previous release mismatch")
    v1.require(release.get("pr") == 119, "PR identity mismatch")
    v1.require(release.get("pr_head") == "eae58ba6443595a5a852f1aad309d7e0f0329fc8", "PR head mismatch")

    target = evidence.get("production_target", {})
    v1.require(target.get("runner") == "hmgweb", "production runner mismatch")
    v1.require(target.get("hostname") == "hmgweb", "production hostname mismatch")
    v1.require(target.get("public_ip") == "20.71.90.212", "production IP mismatch")
    v1.require(target.get("public_origin") == "https://usesafeweb.com", "production origin mismatch")

    deployment = evidence.get("deployment", {})
    v1.require(deployment.get("result") == "PASS", "deployment did not pass")
    v1.require(deployment.get("run_id") == DEPLOY_RUN_ID, "deployment evidence run mismatch")
    v1.require(deployment.get("job_id") == DEPLOY_JOB_ID, "deployment evidence job mismatch")
    v1.require(deployment.get("canonical_deploy_script_blob") == DEPLOY_SCRIPT_BLOB, "deploy script blob mismatch")
    validation = deployment.get("validation", {})
    v1.require(validation.get("contract_tests") == "118/118 PASS", "contract test proof mismatch")
    v1.require(validation.get("typecheck") == "PASS", "typecheck proof mismatch")
    v1.require(validation.get("production_build") == "PASS", "production build proof mismatch")
    v1.require(validation.get("local_health") == "PASS exact target SHA", "local health proof mismatch")
    v1.require(validation.get("public_https_health") == "PASS exact target SHA and TLS verified", "public health proof mismatch")
    v1.require(validation.get("landing") == "PASS", "landing proof mismatch")
    v1.require(validation.get("wordmark") == "PASS", "wordmark proof mismatch")
    v1.require(validation.get("start_route") == "PASS", "start route proof mismatch")
    v1.require(validation.get("setup_route") == "PASS", "setup route proof mismatch")
    v1.require(validation.get("locales") == ["en-GB", "tr-TR", "ar"], "locale proof mismatch")
    v1.require(validation.get("fail_closed_runtime_negative_test") == "PASS", "fail-closed proof mismatch")
    v1.require(validation.get("system_node_npm_unchanged") is True, "system runtime preservation mismatch")

    verify = evidence.get("independent_post_deploy_verification", {})
    v1.require(verify.get("result") == "PASS", "independent verification did not pass")
    v1.require(verify.get("run_id") == VERIFY_RUN_ID, "verification evidence run mismatch")
    v1.require(verify.get("job_id") == VERIFY_JOB_ID, "verification evidence job mismatch")

    browser = evidence.get("accessibility_and_browser_acceptance", {})
    v1.require(browser.get("result") == "PASS", "browser/accessibility evidence did not pass")
    v1.require(browser.get("deployed_merge_commit") == RELEASE_COMMIT, "browser evidence release mismatch")
    v1.require(browser.get("source_to_deployed_compare_changed_files") == 0, "browser-tested/deployed tree drift")
    v1.require(browser.get("run_id") == BROWSER_RUN_ID, "browser evidence run mismatch")
    v1.require(browser.get("job_id") == BROWSER_JOB_ID, "browser evidence job mismatch")
    v1.require(browser.get("browser_marker") == "TSK0395_BROWSER_ACCEPTANCE=PASS", "browser marker mismatch")

    rollback = evidence.get("rollback", {})
    v1.require(rollback.get("available") is True, "rollback availability not proven")
    v1.require(rollback.get("previous_release_retained") == PREVIOUS_RELEASE, "retained rollback release mismatch")
    v1.require(rollback.get("deploy_script_same_for_previous_and_target") is True, "rollback implementation identity mismatch")
    v1.require(rollback.get("deploy_script_blob") == DEPLOY_SCRIPT_BLOB, "rollback script blob mismatch")
    v1.require(isinstance(rollback.get("prior_live_rollback_proof_run"), int), "prior live rollback proof missing")

    v1.require(evidence.get("secrets") == "No secret values are stored in this evidence.", "secret-handling evidence mismatch")


def transition(request, source, source_raw, source_blob, stats):
    validate_evidence()
    target_work = next((wi for wi in source["baseline"]["work_items"] if wi["id"] == TARGET_ID), None)
    target_runtime = next((item for item in source["runtime"]["items"] if item["id"] == TARGET_ID), None)
    v1.require(target_work is not None and target_runtime is not None, f"{TARGET_ID} missing")
    v1.require(source.get("checkpoint_revision") == 55, "source revision drift")
    v1.require(source["baseline"].get("version") == 2, "source baseline drift")
    v1.require(source["runtime"].get("project_status") == "ACTIVE", "project is not ACTIVE")
    v1.require(source["runtime"].get("governance_blocker") is None, "project governance blocker present")
    v1.require(target_work.get("title") == "Deploy production web/application/content release candidate", "target title mismatch")
    v1.require(target_work.get("depends_on") == [], "sequencing override dependency state drift")
    v1.require([ac.get("id") for ac in target_work.get("acceptance_criteria", [])] == [AC_ID], "target acceptance criteria drift")
    v1.require(any(rule.get("id") == "POL-016" for rule in source["baseline"].get("policy_rules", [])), "sequencing override missing")
    v1.require(target_runtime.get("status") == "TODO", "target is not TODO")
    v1.require(target_runtime.get("acceptance_references") == [], "target already has acceptance references")
    v1.require("wait" not in target_runtime, "unexpected target wait payload")
    for constraint in source["runtime"].get("human_constraints", []):
        scoped = constraint.get("scope") == "PROJECT" or TARGET_ID in constraint.get("work_item_ids", [])
        v1.require(not scoped, f"human constraint blocks {TARGET_ID}: {constraint.get('id')}")

    updated = copy.deepcopy(source)
    updated["checkpoint_revision"] = source["checkpoint_revision"] + 1
    for item in updated["runtime"]["items"]:
        if item["id"] == TARGET_ID:
            item["status"] = "PASS"
            item["acceptance_references"] = [copy.deepcopy(ACCEPTANCE_REFERENCE)]
            break

    normalized = copy.deepcopy(updated)
    normalized["checkpoint_revision"] = source["checkpoint_revision"]
    for item in normalized["runtime"]["items"]:
        if item["id"] == TARGET_ID:
            item["status"] = target_runtime["status"]
            item["acceptance_references"] = copy.deepcopy(target_runtime["acceptance_references"])
            break
    v1.require(normalized == source, "production PASS transition attempted unrelated checkpoint mutation")

    new_stats = v1.validate_checkpoint(updated, source["checkpoint_revision"] + 1, source["baseline"]["version"])
    v1.require(new_stats["status_counts"].get("PASS") == stats["status_counts"].get("PASS") + 1, "PASS count did not increment exactly once")
    v1.require(new_stats["status_counts"].get("TODO") == stats["status_counts"].get("TODO") - 1, "TODO count did not decrement exactly once")
    v1.require(new_stats["status_counts"].get("WAITING") == stats["status_counts"].get("WAITING"), "WAITING count changed")
    v1.require(new_stats["status_counts"].get("BLOCKED") == stats["status_counts"].get("BLOCKED"), "BLOCKED count changed")

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
        "release_commit": RELEASE_COMMIT,
        "acceptance_reference": EVIDENCE_REFERENCE,
        "deployment_run_id": DEPLOY_RUN_ID,
        "deployment_job_id": DEPLOY_JOB_ID,
        "verification_run_id": VERIFY_RUN_ID,
        "verification_job_id": VERIFY_JOB_ID,
        "browser_run_id": BROWSER_RUN_ID,
        "browser_job_id": BROWSER_JOB_ID,
        "stable_mutation": (
            "TSK-0468 transitioned from TODO to PASS after exact durable production deployment, independent post-deploy, "
            "browser/accessibility, owner-approval and rollback evidence validation for release 907d3880026ca73be949cfc7ecee14eff3efb60c; "
            "baseline and all unrelated runtime state remain unchanged."
        ),
        "old_bytes": len(source_raw),
        "new_bytes": len(updated_raw),
        "status_counts": new_stats["status_counts"],
    }
    v1.write_json(v1.RESULT, result)


def main():
    request, _ = v1.read_json(v1.REQUEST)
    if request.get("operation") != OPERATION:
        v4.main()
        return
    validate_request(request)
    source, source_raw, source_blob, stats = v1.load_authority(request)
    transition(request, source, source_raw, source_blob, stats)
    print(
        f"CHECKPOINT_ADAPTER_V5_PASS operation={request['operation']} source_blob={source_blob} "
        f"revision={source['checkpoint_revision']} baseline={source['baseline']['version']}"
    )


if __name__ == "__main__":
    main()
