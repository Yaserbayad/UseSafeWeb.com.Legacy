from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

SOURCE_BLOB = "ae203f4b55864f6c0163669dcaf853bcf225a546"
SOURCE_REVISION = 49
TARGET_REVISION = 50
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

raw = SOURCE.read_bytes()
git_blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
assert git_blob == SOURCE_BLOB, (git_blob, SOURCE_BLOB)
source = json.loads(raw.decode("utf-8"))
assert source["checkpoint_schema"] == "serial-light-checkpoint-v1"
assert source["project_id"] == PROJECT_ID
assert source["governance_mode"] == "SERIAL_LIGHT"
assert source["checkpoint_revision"] == SOURCE_REVISION
assert source["baseline"]["version"] == 1
assert source["runtime"]["project_status"] == "ACTIVE"
assert source["runtime"]["governance_blocker"] is None

baseline_items = source["baseline"]["work_items"]
runtime_items = source["runtime"]["items"]
assert len(baseline_items) == len(runtime_items) == 641
baseline_ids = [item["id"] for item in baseline_items]
runtime_ids = [item["id"] for item in runtime_items]
assert baseline_ids == runtime_ids
assert len(set(baseline_ids)) == 641
baseline_map = {item["id"]: item for item in baseline_items}
source_runtime_map = {item["id"]: item for item in runtime_items}
assert source_runtime_map["TSK-0243"]["status"] == "WAITING"

# Exact rollback copy of the source checkpoint.
(ARCHIVE / "CURRENT_STATE_REV49_FULL.json").write_bytes(raw)

candidate = copy.deepcopy(source)
candidate["checkpoint_revision"] = TARGET_REVISION
compact_runtime: list[dict] = []

for original in source["runtime"]["items"]:
    item_id = original["id"]
    if item_id == "TSK-0243":
        ac_ids = [criterion["id"] for criterion in baseline_map[item_id]["acceptance_criteria"]]
        compact_runtime.append(
            {
                "id": item_id,
                "status": "PASS",
                "acceptance_references": [
                    {
                        "ac_id": ac_id,
                        "evidence_type": "GITHUB_BLOB",
                        "reference": (
                            f"Yaserbayad/UseSafeWeb.com {NEW_EVIDENCE_PATH}; "
                            f"blob {NEW_EVIDENCE_BLOB}"
                        ),
                        "summary": (
                            "Production DNS verification, privacy, negative, regression, "
                            "and rollback acceptance proof passed on 2026-09-08."
                        ),
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
                    "Yaserbayad/UseSafeWeb.com CURRENT_STATE.md revision 49; "
                    f"blob {SOURCE_BLOB}#runtime.items/{item_id}/{reference['ac_id']}"
                ),
                "summary": (
                    "Original acceptance proof is preserved in the immutable revision-49 "
                    "checkpoint archive."
                ),
            }
            for reference in references
        ]

    if item.get("status") == "WAITING" and isinstance(item.get("wait"), dict):
        if item["wait"].get("reference"):
            item["wait"]["reference"] = (
                "Yaserbayad/UseSafeWeb.com CURRENT_STATE.md revision 49; "
                f"blob {SOURCE_BLOB}#runtime.items/{item_id}/wait"
            )
    if item.get("status") == "BLOCKED" and isinstance(item.get("blocker"), dict):
        if item["blocker"].get("reference"):
            item["blocker"]["reference"] = (
                "Yaserbayad/UseSafeWeb.com CURRENT_STATE.md revision 49; "
                f"blob {SOURCE_BLOB}#runtime.items/{item_id}/blocker"
            )
    compact_runtime.append(item)

candidate["runtime"]["items"] = compact_runtime

# The project baseline and all project-level runtime controls are byte-semantically unchanged.
assert candidate["baseline"] == source["baseline"]
for key in (
    "project_status",
    "governance_blocker",
    "gate_satisfactions",
    "human_constraints",
    "closure_references",
):
    assert candidate["runtime"][key] == source["runtime"][key]

candidate_runtime_map = {item["id"]: item for item in candidate["runtime"]["items"]}
assert list(candidate_runtime_map) == baseline_ids
assert len(candidate_runtime_map) == 641

for item_id in baseline_ids:
    base = baseline_map[item_id]
    current = candidate_runtime_map[item_id]
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
    elif status == "BLOCKED":
        assert current.get("blocker", {}).get("reason")
        assert current.get("blocker", {}).get("required_resolution")
        assert "wait" not in current
    elif status == "TODO":
        assert "wait" not in current and "blocker" not in current
    else:
        raise AssertionError(status)

source_status = {item["id"]: item["status"] for item in source["runtime"]["items"]}
target_status = {item["id"]: item["status"] for item in candidate["runtime"]["items"]}
changed = {
    item_id: (source_status[item_id], target_status[item_id])
    for item_id in baseline_ids
    if source_status[item_id] != target_status[item_id]
}
assert changed == {"TSK-0243": ("WAITING", "PASS")}, changed

# Build read-only shards. Existing PASS records retain their full original proof details.
archive_runtime_map = {
    item["id"]: copy.deepcopy(item) for item in source["runtime"]["items"]
}
archive_runtime_map["TSK-0243"] = copy.deepcopy(candidate_runtime_map["TSK-0243"])
resulting_status = Counter(target_status.values())
shards: dict[str, list[dict]] = {"PASS": [], "TODO": [], "WAITING": [], "BLOCKED": []}
for item_id in baseline_ids:
    status = target_status[item_id]
    runtime_record = (
        archive_runtime_map[item_id] if status == "PASS" else source_runtime_map[item_id]
    )
    shards[status].append(
        {
            "work_item": copy.deepcopy(baseline_map[item_id]),
            "runtime": copy.deepcopy(runtime_record),
        }
    )


def write_json(path: Path, value: object) -> bytes:
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8", newline="\n")
    return text.encode("utf-8")


done_doc = {
    "format": "usesafeweb-state-archive-v1",
    "project_id": PROJECT_ID,
    "resulting_checkpoint_revision": TARGET_REVISION,
    "source_checkpoint_revision": SOURCE_REVISION,
    "source_checkpoint_blob": SOURCE_BLOB,
    "status": "PASS",
    "count": len(shards["PASS"]),
    "items": shards["PASS"],
}
write_json(ARCHIVE / "DONE_ARCHIVE_REV50.json", done_doc)

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

candidate_bytes = write_json(CANDIDATE_DIR / "CURRENT_STATE_REV50_COMPACT.json", candidate)
assert len(candidate_bytes) < 950_000, (
    f"candidate too large for qualified connector: {len(candidate_bytes)}"
)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


manifest = {
    "format": "usesafeweb-state-migration-manifest-v1",
    "project_id": PROJECT_ID,
    "source": {
        "checkpoint_revision": SOURCE_REVISION,
        "baseline_version": source["baseline"]["version"],
        "git_blob": SOURCE_BLOB,
        "bytes": len(raw),
        "status_counts": dict(sorted(Counter(source_status.values()).items())),
    },
    "candidate": {
        "checkpoint_revision": TARGET_REVISION,
        "baseline_version": candidate["baseline"]["version"],
        "bytes": len(candidate_bytes),
        "sha256": hashlib.sha256(candidate_bytes).hexdigest(),
        "status_counts": dict(sorted(resulting_status.items())),
        "only_status_change": {"TSK-0243": ["WAITING", "PASS"]},
        "baseline_deep_equal": True,
        "work_item_count": len(baseline_ids),
        "runtime_item_count": len(candidate_runtime_map),
    },
    "files": {
        "archive_full_rev49": {
            "path": "State/archive/CURRENT_STATE_REV49_FULL.json",
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
        "baseline_unchanged": True,
        "all_641_ids_preserved_in_order": True,
        "all_open_runtime_payloads_preserved_except_compacted_reference_indirection": True,
        "pass_ac_coverage_complete": True,
        "master_plan_or_wbs_modified": False,
    },
}
write_json(ROOT / "MANIFEST_REV50.json", manifest)

(ROOT / "README.md").write_text(
    "# State split — revision 50 candidate\n\n"
    "This directory is a storage/readability split only. It does not replace or modify "
    "the frozen Master Plan/WBS.\n\n"
    "- `archive/CURRENT_STATE_REV49_FULL.json` is the exact pre-migration checkpoint backup.\n"
    "- `archive/DONE_ARCHIVE_REV50.json` is the large completed/PASS archive.\n"
    "- `open/TODO_REV50.json`, `open/WAITING_REV50.json`, and "
    "`open/BLOCKED_REV50.json` are read-only convenience shards.\n"
    "- `candidate/CURRENT_STATE_REV50_COMPACT.json` is the proposed authoritative checkpoint.\n"
    "- `MANIFEST_REV50.json` records counts, hashes, and preservation assertions.\n\n"
    "Until the candidate is separately verified and written to `CURRENT_STATE.md` through "
    "the qualified GitHub checkpoint update, revision 49 remains authoritative.\n",
    encoding="utf-8",
    newline="\n",
)

print("MIGRATION_CANDIDATE=PASS")
print(f"SOURCE_BLOB={SOURCE_BLOB}")
print(f"SOURCE_BYTES={len(raw)}")
print(f"CANDIDATE_BYTES={len(candidate_bytes)}")
print(f"STATUS_COUNTS={dict(sorted(resulting_status.items()))}")
print(f"DONE_COUNT={len(shards['PASS'])}")
print(f"TODO_COUNT={len(shards['TODO'])}")
print(f"WAITING_COUNT={len(shards['WAITING'])}")
print(f"BLOCKED_COUNT={len(shards['BLOCKED'])}")
