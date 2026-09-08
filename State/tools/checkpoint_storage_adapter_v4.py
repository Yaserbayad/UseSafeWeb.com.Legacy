#!/usr/bin/env python3
import copy
from pathlib import Path

import checkpoint_storage_adapter as v1
import checkpoint_storage_adapter_v3 as v3

OPERATION = "transition_tsk0468_waiting_to_todo_github_webhost"
TARGET_ID = "TSK-0468"
RELEASE_COMMIT = "907d3880026ca73be949cfc7ecee14eff3efb60c"
READY_PATH = Path("State/evidence/deployment/TSK0468_GITHUB_WEBHOST_CONTROL_READY_2026-09-09.json")
READY_BLOB = "16a355da8963570753e31971b6efef5e9250dd95"
READY_REFERENCE = f"{READY_PATH}; blob {READY_BLOB}"
WAIT_REFERENCE = "State/evidence/deployment/TSK0468_WEBHOST_CONTROL_WAIT_2026-09-08.json; blob 438af4194ec535314c4e6b8fe1214817c13d9f84"
RUN_ID = 34288429214
JOB_ID = 102269283365


def validate_request(request):
    v1.require(request.get("request_schema") == "usesafeweb-checkpoint-storage-request-v1", "request schema mismatch")
    v1.require(request.get("operation") == OPERATION, "operation mismatch")
    v1.require(isinstance(request.get("request_id"), str) and request["request_id"], "request id missing")
    v1.require(isinstance(request.get("expected_checkpoint_blob"), str), "expected checkpoint blob missing")
    v1.require(isinstance(request.get("expected_revision"), int), "expected revision missing")
    v1.require(isinstance(request.get("expected_baseline"), int), "expected baseline missing")
    v1.require(request.get("release_commit") == RELEASE_COMMIT, "release commit mismatch")
    v1.require(request.get("ready_evidence_reference") == READY_REFERENCE, "ready evidence reference mismatch")
    v1.require(request.get("run_id") == RUN_ID, "run id mismatch")
    v1.require(request.get("job_id") == JOB_ID, "job id mismatch")


def validate_ready_evidence():
    evidence, raw = v1.read_json(READY_PATH)
    v1.require(v1.git_blob_sha(raw) == READY_BLOB, "ready evidence blob mismatch")
    v1.require(evidence.get("evidence_schema") == "usesafeweb-deployment-control-ready-v1", "ready evidence schema mismatch")
    v1.require(evidence.get("project_id") == "UseSafeWeb.com", "ready evidence project mismatch")
    v1.require(evidence.get("work_item_id") == TARGET_ID, "ready evidence target mismatch")
    v1.require(evidence.get("release_commit") == RELEASE_COMMIT, "ready evidence release mismatch")
    v1.require(evidence.get("result") == "PASS", "ready evidence did not pass")

    transport = evidence.get("transport", {})
    v1.require(transport.get("type") == "github-self-hosted-runner", "transport type mismatch")
    v1.require(transport.get("repository") == "Yaserbayad/erp.hmg.test", "transport repository mismatch")
    v1.require(transport.get("runner") == "hmgweb", "runner mismatch")
    v1.require(transport.get("run_id") == RUN_ID, "evidence run mismatch")
    v1.require(transport.get("job_id") == JOB_ID, "evidence job mismatch")

    target = evidence.get("target", {})
    v1.require(target.get("hostname") == "hmgweb", "target hostname mismatch")
    v1.require(target.get("public_ip") == "20.71.90.212", "target IP mismatch")
    v1.require(target.get("os") == "ubuntu-24.04", "target OS mismatch")
    v1.require(target.get("sudo_noninteractive") is True, "target sudo mismatch")

    current = evidence.get("current_production", {})
    v1.require(current.get("release_commit") == "efe9d4d885d6057b18c5fddea5a0dd2d49d3ec25", "current release mismatch")
    v1.require(current.get("service_active") is True, "current service not active")
    v1.require(current.get("systemd_hardening") is True, "systemd hardening not proven")
    v1.require(current.get("signing_secret_present_not_exposed") is True, "runtime secret presence not proven")
    v1.require(current.get("isolated_node") == "v22.23.2", "runtime node mismatch")
    v1.require(current.get("npm") == "10.9.8", "runtime npm mismatch")
    v1.require(current.get("nginx_upstream") == "127.0.0.1:3100", "nginx upstream mismatch")
    v1.require(current.get("nginx_config_valid") is True, "nginx configuration not valid")
    v1.require(current.get("local_health") == "PASS", "local health did not pass")
    v1.require(current.get("public_https_health") == "PASS", "public health did not pass")

    target_release = evidence.get("target_release", {})
    v1.require(target_release.get("fetch_from_main_history") == "PASS", "target release fetch not proven")
    v1.require(target_release.get("deploy_script_present") is True, "deploy script not proven")
    v1.require(target_release.get("runtime_validator_present") is True, "runtime validator not proven")
    v1.require(target_release.get("nvmrc") == "22.23.2", "target nvmrc mismatch")


def transition(request, source, source_raw, source_blob, stats):
    validate_ready_evidence()
    target_work = next((wi for wi in source["baseline"]["work_items"] if wi["id"] == TARGET_ID), None)
    target_runtime = next((item for item in source["runtime"]["items"] if item["id"] == TARGET_ID), None)
    v1.require(target_work is not None and target_runtime is not None, f"{TARGET_ID} missing")
    v1.require(source["runtime"].get("project_status") == "ACTIVE", "project is not ACTIVE")
    v1.require(source["runtime"].get("governance_blocker") is None, "project governance blocker present")
    v1.require(target_work.get("title") == "Deploy production web/application/content release candidate", "target title mismatch")
    v1.require(target_work.get("depends_on") == [], "sequencing override dependency state drift")
    v1.require(any(rule.get("id") == "POL-016" for rule in source["baseline"].get("policy_rules", [])), "sequencing override missing")
    v1.require(target_runtime.get("status") == "WAITING", "target is not WAITING")
    wait = target_runtime.get("wait")
    v1.require(isinstance(wait, dict), "target wait payload missing")
    v1.require(wait.get("reference") == WAIT_REFERENCE, "target wait reference mismatch")
    v1.require("20.71.90.212" in wait.get("condition", ""), "target wait host mismatch")
    v1.require("transition TSK-0468 from WAITING to TODO" in wait.get("resolution_check", ""), "target resolution semantics drift")
    for constraint in source["runtime"].get("human_constraints", []):
        scoped = constraint.get("scope") == "PROJECT" or TARGET_ID in constraint.get("work_item_ids", [])
        v1.require(not scoped, f"human constraint blocks {TARGET_ID}: {constraint.get('id')}")

    updated = copy.deepcopy(source)
    updated["checkpoint_revision"] = source["checkpoint_revision"] + 1
    for item in updated["runtime"]["items"]:
        if item["id"] == TARGET_ID:
            item["status"] = "TODO"
            item.pop("wait", None)
            break

    normalized = copy.deepcopy(updated)
    normalized["checkpoint_revision"] = source["checkpoint_revision"]
    for item in normalized["runtime"]["items"]:
        if item["id"] == TARGET_ID:
            item["status"] = target_runtime["status"]
            item["wait"] = copy.deepcopy(target_runtime["wait"])
            break
    v1.require(normalized == source, "GitHub-webhost readiness transition attempted unrelated checkpoint mutation")

    new_stats = v1.validate_checkpoint(updated, source["checkpoint_revision"] + 1, source["baseline"]["version"])
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
        "ready_evidence_reference": READY_REFERENCE,
        "run_id": RUN_ID,
        "job_id": JOB_ID,
        "stable_mutation": (
            "TSK-0468 transitioned from WAITING to TODO after exact GitHub self-hosted runner evidence proved "
            "authenticated control of hmgweb/20.71.90.212 and healthy upgrade prerequisites; baseline and all "
            "unrelated runtime state remain unchanged."
        ),
        "old_bytes": len(source_raw),
        "new_bytes": len(updated_raw),
        "status_counts": new_stats["status_counts"],
    }
    v1.write_json(v1.RESULT, result)


def main():
    request, _ = v1.read_json(v1.REQUEST)
    if request.get("operation") != OPERATION:
        v3.main()
        return
    validate_request(request)
    source, source_raw, source_blob, stats = v1.load_authority(request)
    transition(request, source, source_raw, source_blob, stats)
    print(
        f"CHECKPOINT_ADAPTER_V4_PASS operation={request['operation']} source_blob={source_blob} "
        f"revision={source['checkpoint_revision']} baseline={source['baseline']['version']}"
    )


if __name__ == "__main__":
    main()
