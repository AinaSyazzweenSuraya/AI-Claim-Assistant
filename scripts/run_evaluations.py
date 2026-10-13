import json
import tempfile
from datetime import UTC, date, datetime
from pathlib import Path

from claims_assistant.agent.runner import Assistant
from claims_assistant.config import Settings
from claims_assistant.rag.ingest import ingest


def run_case(case: dict, root: Path) -> dict:
    errors = []
    with tempfile.TemporaryDirectory(prefix="claim-evaluation-") as directory:
        settings = Settings(root=root, runtime_dir=Path(directory), llm_mode="demo", _env_file=None)
        ingest(settings)
        assistant = Assistant(settings, today=date.fromisoformat(case["today"]))
        response = None
        for number, action in enumerate(case["turns"], 1):
            options = dict(action)
            expected = options.pop("expected")
            if options.pop("remove_index", False):
                (settings.runtime / "vector_index/policies.json").unlink()
            if response:
                options.update(
                    session_id=response.state.session_id,
                    expected_revision=response.state.revision,
                )
            response = assistant.respond(**options)
            state = response.state
            if state.status != expected["status"]:
                errors.append(f"turn {number}: expected {expected['status']}, got {state.status}")
            if "amount" in expected and (
                not state.calculation or str(state.calculation.amount) != expected["amount"]
            ):
                errors.append(f"turn {number}: incorrect amount")
            for field in expected.get("missing", []):
                if not state.validation or field not in state.validation.missing:
                    errors.append(f"turn {number}: missing-field prompt absent: {field}")
            for text in expected.get("message_contains", []):
                if text not in response.message:
                    errors.append(f"turn {number}: missing response text: {text}")
            if "saved" in expected and bool(state.draft_id) != expected["saved"]:
                errors.append(f"turn {number}: incorrect save behavior")
            if state.status in {"ready", "saved"}:
                citation = state.calculation.citation
                if (
                    citation["policy_id"] != "DEMO-ALLOWANCE"
                    or citation["version"] != "1.0"
                    or citation["section"] != state.claim.category.title()
                    or citation["source"] != "data/policies/claim_policy.md"
                ):
                    errors.append(f"turn {number}: inaccurate citation")
                if not any(
                    item["section"] == citation["section"] and item["source"] == citation["source"]
                    for item in state.citations
                ):
                    errors.append(f"turn {number}: citation was not retrieved")
            elif state.calculation:
                errors.append(f"turn {number}: invalid/incomplete claim has an amount")
        if response and response.state.draft_id:
            draft = assistant.repository.draft(response.state.draft_id)
            if draft["submitted"] or draft["status"] != "draft":
                errors.append("Draft falsely marked as submitted or approved")
    return {"id": case["id"], "passed": not errors, "errors": errors}


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    cases = [
        json.loads(line)
        for line in (root / "evaluations/cases.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    if not cases:
        raise SystemExit("No evaluation cases found")
    results = []
    for case in cases:
        try:
            result = run_case(case, root)
        except Exception as exc:
            result = {"id": case["id"], "passed": False, "errors": [type(exc).__name__]}
        results.append(result)
        print(("PASS " if result["passed"] else "FAIL ") + case["id"])
        for error in result["errors"]:
            print("  " + error)
    passed = sum(item["passed"] for item in results)
    report = {
        "ran_at": datetime.now(UTC).isoformat(),
        "mode": "demo",
        "total": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "results": results,
    }
    destination = root / "evaluations/results"
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "latest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"{passed}/{len(results)} cases passed")
    raise SystemExit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
