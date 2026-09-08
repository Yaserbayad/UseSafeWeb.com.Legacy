from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

SOURCE_BLOB = "ae203f4b55864f6c0163669dcaf853bcf225a546"
SOURCE_REVISION = 49
SOURCE_BASELINE_VERSION = 1
TARGET_REVISION = 50
TARGET_BASELINE_VERSION = 2
PROJECT_ID = "UseSafeWeb.com"
NEW_EVIDENCE_BLOB = "a204a2f2aa4ea8463a539c740e58aa72f31ef9d6"
NEW_EVIDENCE_PATH = "TSK_0243_DNS_VERIFICATION_EVIDENCE_2026-09-08.md"
SOURCE = Path("CURRENT_STATE.md")
ROOT = Path("State")
ARCHIVE = ROOT / "archive"
OPEN = ROOT / "open"
CANDIDATE_DIR = ROOT / "candidate"

for directory in (ARCHIVE, OPEN, CANDIDATE_DIR):
    directory.mkdir(parents=True, exist_ok=True)


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def write_json(path: Path, value: object) -> bytes:
    data = canonical_bytes(value)
    path.write_bytes(data)
    return data


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


raw = SOURCE.read_bytes()
git_blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
assert git_blob == SOURCE_BLOB, (git_blob, SOURCE_BLOB)
source = json.loads(raw.decode("utf-8"))
assert source["checkpoint_schema"] == "serial-light-checkpoint-v1"
assert source["project_id"] == PROJECT_ID
assert source["governance_mode"] == "SERIAL_LIGHT"
assert source["checkpoint_revision"] == SOURCE_REVISION
assert source["baseline"]["version"] == SOURCE_BASELINE_VERSION
assert source["runtime"]["project_status"] == "ACTIVE"
assert source["runtime"]["governance_blocker"] is None
assert source["runtime"]["human_constraints"] == []

baseline_items = source["baseline"]["work_items"]
runtime_items = source["runtime"]["items"]
assert len(baseline_items) == len(runtime_items) == 641
baseline_ids = [item["id"] for item in baseline_items]
runtime_ids = [item["id"] for item in runtime_items]
assert baseline_ids == runtime_ids
assert len(set(baseline_ids)) == 641
source_baseline = {item["id"]: item for item in baseline_items}
source_runtime = {item["id"]: item for item in runtime_items}
source_status = {item["id"]: item["status"] for item in runtime_items}
assert source_status["TSK-0243"] == "WAITING"
assert Counter(source_status.values()) == Counter({"WAITING": 380, "PASS": 261})

# Immutable exact rollback archive of the pre-migration checkpoint.
(ARCHIVE / "CURRENT_STATE_REV49_FULL.json").write_bytes(raw)
assert hashlib.sha1(
    f"blob {len((ARCHIVE / 'CURRENT_STATE_REV49_FULL.json').read_bytes())}\0".encode()
    + (ARCHIVE / "CURRENT_STATE_REV49_FULL.json").read_bytes()
).hexdigest() == SOURCE_BLOB

candidate = copy.deepcopy(source)
candidate["checkpoint_revision"] = TARGET_REVISION
candidate["baseline"]["version"] = TARGET_BASELINE_VERSION

# Storage-only baseline reduction: for work already PASS after this migration, remove only
# optional per-item spec_reference strings. Full records remain in the immutable archives.
# Non-PASS work-item definitions remain exactly unchanged.
resulting_status = dict(source_status)
resulting_status["TSK-0243"] = "PASS"
for target_item in candidate["baseline"]["work_items"]:
    if resulting_status[target_item["id"]] == "PASS":
        target_item.pop("spec_reference", None)

compact_runtime: list[dict] = []
for original in source["runtime"]["items"]:
    item_id = original["id"]
    if item_id == "TSK-0243":
        ac_ids = [
            criterion["id"] for criterion in source_baseline[item_id]["acceptance_criteria"]
        ]
        compact_runtime.append(
            {
                "id": item_id,
                "status": "PASS",
                "acceptance_references": [
                    {
                        "ac_id": ac_id,
                        "evidence_type": "GITHUB_BLOB",
                        "reference": (
                            f"Yaserbayad/UseSafeWeb.com@{NEW_EVIDENCE_BLOB}:"
                            f"{NEW_EVIDENCE_PATH}"
                        ),
                        "summary": "Verified production DNS acceptance proof.",
                    }
                    for ac_id in ac_ids
                ],
            }
        )
        continue

    item = copy.deepcopy(original)
    references = item.get("acceptance_references", [])
    if references:
        item["acceptance_references"] = [
            {
                "ac_id": reference["ac_id"],
                "evidence_type": "GITHUB_BLOB",
                "reference": (
                    f"Yaserbayad/UseSafeWeb.com@{SOURCE_BLOB}#"
                    f"{item_id}/{reference['ac_id']}"
                ),
                "summary": "Proof preserved in immutable rev49 archive.",
            }
            for reference in references
        ]

    # WAITING/BLOCKED semantics stay verbatim. Only optional historical reference bodies move
    # to the read-only shards/full archive; the actionable condition/resolution remains local.
    if item.get("status") == "WAITING" and isinstance(item.get("wait"), dict):
        item["wait"].pop("reference", None)
    if item.get("status") == "BLOCKED" and isinstance(item.get("blocker"), dict):
        item["blocker"].pop("reference", None)
    compact_runtime.append(item)

candidate["runtime"]["items"] = compact_runtime
candidate_baseline = {item["id"]: item for item in candidate["baseline"]["work_items"]}
candidate_runtime = {item["id"]: item for item in candidate["runtime"]["items"]}
assert list(candidate_baseline) == baseline_ids
assert list(candidate_runtime) == baseline_ids

# Project-level authority/state fields stay unchanged except the authorized version counters.
for key in ("objectives", "policy_rules", "gates", "closure_criteria"):
    assert candidate["baseline"][key] == source["baseline"][key]
for key in (
    "project_status",
    "governance_blocker",
    "gate_satisfactions",
    "human_constraints",
    "closure_references",
):
    assert candidate["runtime"][key] == source["runtime"][key]

# Baseline impact proof: open work is exact; PASS work differs only by optional spec_reference.
for item_id in baseline_ids:
    before = source_baseline[item_id]
    after = candidate_baseline[item_id]
    if resulting_status[item_id] != "PASS":
        assert after == before, item_id
    else:
        expected = copy.deepcopy(before)
        expected.pop("spec_reference", None)
        assert after == expected, item_id

# Runtime impact proof: one status transition only. Open actionable semantics are unchanged.
target_status = {item["id"]: item["status"] for item in candidate["runtime"]["items"]}
changed = {
    item_id: (source_status[item_id], target_status[item_id])
    for item_id in baseline_ids
    if source_status[item_id] != target_status[item_id]
}
assert changed == {"TSK-0243": ("WAITING", "PASS")}, changed
assert Counter(target_status.values()) == Counter({"WAITING": 379, "PASS": 262})

for item_id in baseline_ids:
    base = candidate_baseline[item_id]
    current = candidate_runtime[item_id]
    ac_ids = [criterion["id"] for criterion in base["acceptance_criteria"]]
    ref_ids = [reference["ac_id"] for reference in current.get("acceptance_references", [])]
    assert len(ref_ids) == len(set(ref_ids))
    assert set(ref_ids).issubset(set(ac_ids))
    status = current["status"]
    if status == "PASS":
        assert sorted(ref_ids) == sorted(ac_ids)
        assert "wait" not in current
        assert "blocker" not in current
        assert "continuation_note" not in current
    elif status == "WAITING":
        assert current.get("wait", {}).get("condition")
        assert current.get("wait", {}).get("resolution_check")
        assert "blocker" not in current
        # Condition + resolution are exact source semantics; only optional reference is omitted.
        original_wait = source_runtime[item_id]["wait"]
        assert current["wait"]["condition"] == original_wait["condition"]
        assert current["wait"]["resolution_check"] == original_wait["resolution_check"]
    elif status == "BLOCKED":
        assert current.get("blocker", {}).get("reason")
        assert current.get("blocker", {}).get("required_resolution")
        assert "wait" not in current
    elif status == "TODO":
        assert "wait" not in current and "blocker" not in current
    else:
        raise AssertionError(status)

# Read-only lossless state shards use the full original baseline/runtime records.
archive_runtime = {
    item["id"]: copy.deepcopy(item) for item in source["runtime"]["items"]
}
archive_runtime["TSK-0243"] = copy.deepcopy(candidate_runtime["TSK-0243"])
shards: dict[str, list[dict]] = {"PASS": [], "TODO": [], "WAITING": [], "BLOCKED": []}
for item_id in baseline_ids:
    status = target_status[item_id]
    runtime_record = (
        archive_runtime[item_id] if status == "PASS" else source_runtime[item_id]
    )
    shards[status].append(
        {
            "work_item": copy.deepcopy(source_baseline[item_id]),
            "runtime": copy.deepcopy(runtime_record),
        }
    )

write_json(
    ARCHIVE / "DONE_ARCHIVE_REV50.json",
    {
        "format": "usesafeweb-state-archive-v1",
        "project_id": PROJECT_ID,
        "resulting_checkpoint_revision": TARGET_REVISION,
        "source_checkpoint_revision": SOURCE_REVISION,
        "source_checkpoint_blob": SOURCE_BLOB,
        "status": "PASS",
        "count": len(shards["PASS"]),
        "items": shards["PASS"],
    },
)
for status in ("TODO", "WAITING", "BLOCKED"):
    write_json(
        OPEN / f"{status}_REV50.json",
        {
            "format": "usesafeweb-open-state-shard-v1",
            "project_id": PROJECT_ID,
            "resulting_checkpoint_revision": TARGET_REVISION,
            "source_checkpoint_blob": SOURCE_BLOB,
            "status": status,
            "count": len(shards[status]),
            "items": shards[status],
        },
    )

candidate_bytes = write_json(
    CANDIDATE_DIR / "CURRENT_STATE_REV50_COMPACT.json", candidate
)
# Keep a safety margin below GitHub Contents API's 1 MiB ceiling.
assert len(candidate_bytes) < 980_000, (
    f"candidate too large for qualified connector: {len(candidate_bytes)}"
)

manifest = {
    "format": "usesafeweb-state-migration-manifest-v1",
    "project_id": PROJECT_ID,
    "authorization": (
        "Owner authorized splitting the oversized project state into a large done archive "
        "and smaller active/read-only state files on 2026-09-08; Master Plan/WBS scope and "
        "semantics remain unchanged."
    ),
    "source": {
        "checkpoint_revision": SOURCE_REVISION,
        "baseline_version": SOURCE_BASELINE_VERSION,
        "git_blob": SOURCE_BLOB,
        "bytes": len(raw),
        "status_counts": dict(sorted(Counter(source_status.values()).items())),
    },
    "candidate": {
        "checkpoint_revision": TARGET_REVISION,
        "baseline_version": TARGET_BASELINE_VERSION,
        "bytes": len(candidate_bytes),
        "sha256": hashlib.sha256(candidate_bytes).hexdigest(),
        "status_counts": dict(sorted(Counter(target_status.values()).items())),
        "only_status_change": {"TSK-0243": ["WAITING", "PASS"]},
        "work_item_count": len(baseline_ids),
        "runtime_item_count": len(candidate_runtime),
    },
    "representation_delta": {
        "pass_work_items": "optional spec_reference omitted from active checkpoint only",
        "waiting_blocked_runtime": (
            "optional historical reference omitted; condition/resolution text preserved exactly"
        ),
        "acceptance_proof": (
            "full original proof preserved in immutable revision-49 archive; active binding "
            "reduced to immutable blob reference and compact summary"
        ),
        "master_plan_wbs": "unchanged",
    },
    "files": {
        "archive_full_rev49": {
            "path": "State/archive/CURRENT_STATE_REV49_FULL.json",
            "git_blob": SOURCE_BLOB,
            "sha256": sha256_file(ARCHIVE / "CURRENT_STATE_REV49_FULL.json"),
        },
        "done_archive": {
            "path": "State/archive/DONE_ARCHIVE_REV50.json",
            "count": len(shards["PASS"]),
            "sha256": sha256_file(ARCHIVE / "DONE_ARCHIVE_REV50.json"),
        },
        "todo": {"path": "State/open/TODO_REV50.json", "count": len(shards["TODO"])},
        "waiting": {
            "path": "State/open/WAITING_REV50.json",
            "count": len(shards["WAITING"]),
        },
        "blocked": {
            "path": "State/open/BLOCKED_REV50.json",
            "count": len(shards["BLOCKED"]),
        },
        "candidate": {"path": "State/candidate/CURRENT_STATE_REV50_COMPACT.json"},
    },
    "preservation_checks": {
        "source_blob_exact": True,
        "identity_and_mode_unchanged": True,
        "all_641_ids_preserved_in_order": True,
        "non_pass_baseline_records_exact": True,
        "pass_baseline_semantics_unchanged_except_optional_reference_omission": True,
        "waiting_conditions_and_resolution_checks_exact": True,
        "pass_ac_coverage_complete": True,
        "full_removed_detail_archived": True,
        "master_plan_or_wbs_modified": False,
    },
}
write_json(ROOT / "MANIFEST_REV50.json", manifest)

(ROOT / "README.md").write_text(
    "# UseSafeWeb state split — revision 50\n\n"
    "This directory archives state detail so the authoritative checkpoint remains small "
    "enough for the normal GitHub connector. It does not modify the frozen Master Plan/WBS.\n\n"
    "- `archive/CURRENT_STATE_REV49_FULL.json`: exact pre-migration checkpoint/rollback copy.\n"
    "- `archive/DONE_ARCHIVE_REV50.json`: full completed/PASS records.\n"
    "- `open/TODO_REV50.json`, `open/WAITING_REV50.json`, `open/BLOCKED_REV50.json`: "
    "read-only state shards with full source detail.\n"
    "- `candidate/CURRENT_STATE_REV50_COMPACT.json`: proposed authoritative checkpoint.\n"
    "- `MANIFEST_REV50.json`: counts, hashes, authorization, and preservation assertions.\n\n"
    "Only `CURRENT_STATE.md` on `main` is authoritative after qualified promotion. These "
    "archive/shard files preserve detail and recovery evidence; they do not independently "
    "control project state.\n",
    encoding="utf-8",
    newline="\n",
)

print("MIGRATION_CANDIDATE=PASS")
print(f"SOURCE_BLOB={SOURCE_BLOB}")
print(f"SOURCE_BYTES={len(raw)}")
print(f"CANDIDATE_BYTES={len(candidate_bytes)}")
print(f"STATUS_COUNTS={dict(sorted(Counter(target_status.values()).items()))}")
print(f"DONE_COUNT={len(shards['PASS'])}")
print(f"TODO_COUNT={len(shards['TODO'])}")
print(f"WAITING_COUNT={len(shards['WAITING'])}")
print(f"BLOCKED_COUNT={len(shards['BLOCKED'])}")
