"""
NetSage AI - Deterministic Rule Checker

Checks:
1. AI diagnosis JSON structure and human-review safety
2. Duplicate IP addresses
3. Invalid/wrong subnet masks
4. Default gateway mismatch
5. Interfaces down
6. Missing VLANs
7. Missing routes
"""

import argparse
import csv
import ipaddress
import json
import re
import sys

REQUIRED_FIELDS = [
    "root_cause", "confidence", "evidence",
    "next_command", "osi_layer", "fix_steps"
]

VALID_CONFIDENCE = {"low", "medium", "high"}

FORBIDDEN_AUTO_APPLY_PHRASES = [
    "i have applied", "i've applied", "i configured this for you",
    "change has been deployed", "automatically fixed", "i already fixed"
]

IOS_COMMAND_HINTS = [
    "show ", "debug ", "ping ", "traceroute ",
    "interface ", "configure terminal", "copy "
]


def add_result(results, check, passed, message):
    results.append({
        "check": check,
        "pass": passed,
        "message": message
    })


def check_diagnosis(diagnosis, raw_evidence_text=""):
    results = []

    for field in REQUIRED_FIELDS:
        present = field in diagnosis and diagnosis[field] not in (None, "", [])
        add_result(
            results,
            f"required_field:{field}",
            present,
            "Present" if present else f"Missing required field: {field}"
        )

    confidence = str(diagnosis.get("confidence", "")).lower()
    add_result(
        results,
        "valid_confidence",
        confidence in VALID_CONFIDENCE,
        f"Confidence is '{confidence}'"
    )

    evidence = diagnosis.get("evidence", [])
    if confidence == "high":
        valid_evidence = isinstance(evidence, list) and len(evidence) > 0
        add_result(
            results,
            "high_confidence_has_evidence",
            valid_evidence,
            "High confidence has evidence" if valid_evidence else
            "High confidence requires evidence"
        )

    if raw_evidence_text and isinstance(evidence, list):
        raw_lower = raw_evidence_text.lower()
        traceable = True

        for item in evidence:
            words = re.findall(r"[a-zA-Z0-9./]+", str(item).lower())
            useful_words = [word for word in words if len(word) > 4]

            if useful_words and not any(word in raw_lower for word in useful_words):
                traceable = False

        add_result(
            results,
            "evidence_traceable",
            traceable,
            "Evidence refers to case output" if traceable else
            "Some AI evidence may not match the show-command output"
        )

    next_command = str(diagnosis.get("next_command", "")).lower()
    plausible_command = any(hint in next_command for hint in IOS_COMMAND_HINTS)

    add_result(
        results,
        "next_command_plausible",
        plausible_command,
        f"Next command: {diagnosis.get('next_command', '')}"
    )

    fix_steps = diagnosis.get("fix_steps", [])
    fix_text = " ".join(fix_steps).lower() if isinstance(fix_steps, list) else str(fix_steps).lower()

    auto_apply = any(phrase in fix_text for phrase in FORBIDDEN_AUTO_APPLY_PHRASES)

    add_result(
        results,
        "human_review_safety",
        not auto_apply,
        "No automatic change claimed" if not auto_apply else
        "AI claims it made a network change without human approval"
    )

    return results


def check_network_config(config):
    results = []

    used_ips = {}

    for host in config.get("hosts", []):
        name = host.get("name", "Unknown host")
        ip = host.get("ip", "")
        mask = host.get("mask", "")
        gateway = host.get("gateway", "")
        expected_mask = host.get("expected_mask", "")

        if ip in used_ips:
            add_result(
                results,
                "duplicate_ip",
                False,
                f"{name} and {used_ips[ip]} both use IP address {ip}"
            )
        elif ip:
            used_ips[ip] = name

        try:
            network = ipaddress.IPv4Network(f"{ip}/{mask}", strict=False)
            add_result(
                results,
                "valid_subnet_mask",
                True,
                f"{name}: {mask} is a valid subnet mask"
            )

            if gateway:
                gateway_ip = ipaddress.IPv4Address(gateway)
                gateway_correct = gateway_ip in network

                add_result(
                    results,
                    "gateway_match",
                    gateway_correct,
                    f"{name}: gateway {gateway} is {'inside' if gateway_correct else 'outside'} subnet {network}"
                )

        except ValueError:
            add_result(
                results,
                "valid_ip_and_mask",
                False,
                f"{name}: invalid IP address or subnet mask ({ip}/{mask})"
            )

        if expected_mask:
            correct_mask = mask == expected_mask

            add_result(
                results,
                "expected_subnet_mask",
                correct_mask,
                f"{name}: configured mask {mask}, expected {expected_mask}"
            )

    for interface in config.get("interfaces", []):
        device = interface.get("device", "Device")
        name = interface.get("name", "Unknown interface")
        status = str(interface.get("status", "")).lower()

        is_up = status in {"up", "up/up", "connected"}

        add_result(
            results,
            "interface_status",
            is_up,
            f"{device} {name}: status is {status}"
        )

    defined_vlans = set(config.get("defined_vlans", []))
    required_vlans = config.get("required_vlans", [])

    for vlan in required_vlans:
        exists = vlan in defined_vlans

        add_result(
            results,
            "required_vlan_exists",
            exists,
            f"VLAN {vlan} is {'defined' if exists else 'missing'}"
        )

    configured_routes = " ".join(config.get("routes", []))
    required_routes = config.get("required_routes", [])

    for route in required_routes:
        exists = route in configured_routes

        add_result(
            results,
            "required_route_exists",
            exists,
            f"Route {route} is {'present' if exists else 'missing'}"
        )

    return results


def check_agreement(diagnosis, expected_fault):
    root_cause = str(diagnosis.get("root_cause", "")).lower()
    expected = str(expected_fault).lower()

    expected_words = {w for w in re.findall(r"[a-z0-9]+", expected) if len(w) > 4}
    root_cause_words = set(re.findall(r"[a-z0-9]+", root_cause))

    overlap = expected_words & root_cause_words
    agrees = len(overlap) > 0

    return agrees, sorted(overlap)


def load_case(cases_csv_path, case_id):
    with open(cases_csv_path, newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            if row["case_id"] == case_id:
                return row

    raise ValueError(f"Case {case_id} not found in {cases_csv_path}")


def print_results(results):
    failed = 0

    for result in results:
        mark = "PASS" if result["pass"] else "FAIL"
        print(f"[{mark}] {result['check']}: {result['message']}")

        if not result["pass"]:
            failed += 1

    return failed


def run_batch(cases_csv_path, diagnoses_json_path, output_csv_path):
    with open(diagnoses_json_path, encoding="utf-8") as file:
        raw_diagnoses = json.load(file)

    # Convert List of objects to Dictionary if required
    all_diagnoses = {}
    if isinstance(raw_diagnoses, list):
        for diag in raw_diagnoses:
            if isinstance(diag, dict) and "case_id" in diag:
                all_diagnoses[diag["case_id"]] = diag
    elif isinstance(raw_diagnoses, dict):
        all_diagnoses = raw_diagnoses

    with open(cases_csv_path, newline="", encoding="utf-8") as file:
        cases = list(csv.DictReader(file))

    rows = []

    for case in cases:
        case_id = case["case_id"]
        diagnosis = all_diagnoses.get(case_id)

        if diagnosis is None:
            rows.append({
                "case_id": case_id,
                "concept": case.get("concept", ""),
                "checks_passed": "",
                "checks_failed": "",
                "agrees_with_expected": "",
                "overall_result": "NO_DIAGNOSIS"
            })
            continue

        results = check_diagnosis(diagnosis, case.get("show_command_output", ""))
        agrees, _ = check_agreement(diagnosis, case.get("expected_fault", ""))
        add_result(
            results,
            "agrees_with_expected_fault",
            agrees,
            ""
        )

        passed = sum(1 for r in results if r["pass"])
        failed = sum(1 for r in results if not r["pass"])

        rows.append({
            "case_id": case_id,
            "concept": case.get("concept", ""),
            "checks_passed": passed,
            "checks_failed": failed,
            "agrees_with_expected": agrees,
            "overall_result": "PASS" if failed == 0 else "FAIL"
        })

    with open(output_csv_path, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=[
            "case_id", "concept", "checks_passed",
            "checks_failed", "agrees_with_expected", "overall_result"
        ])
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows)
    diagnosed = sum(1 for r in rows if r["overall_result"] != "NO_DIAGNOSIS")
    agreed = sum(1 for r in rows if r["agrees_with_expected"] is True)

    print(f"Batch check complete: {diagnosed}/{total} cases had a diagnosis.")
    if diagnosed:
        print(f"AI agreement rate: {agreed}/{diagnosed} ({100 * agreed / diagnosed:.0f}%)")
    print(f"Summary written to {output_csv_path}")


def main():
    parser = argparse.ArgumentParser(
        description="NetSage AI deterministic diagnosis and network rule checker"
    )

    parser.add_argument("--case", default="cases.csv")
    parser.add_argument("--case-id", help="Run a single case (requires --diagnosis)")
    parser.add_argument("--diagnosis", help="Path to a single diagnosis JSON file")
    parser.add_argument(
        "--network-config",
        help="Optional network_snapshot.json file for duplicate IP, VLAN, route, mask, gateway, and interface checks"
    )
    parser.add_argument(
        "--all",
        metavar="ai_diagnoses.json",
        help="Run every case against a JSON file of {case_id: diagnosis} or list of diagnoses and write a summary CSV"
    )
    parser.add_argument(
        "--output",
        default="rule_checker_summary.csv",
        help="Where to write the batch summary CSV (used with --all)"
    )

    args = parser.parse_args()

    if args.all:
        run_batch(args.case, args.all, args.output)
        return

    if not args.case_id or not args.diagnosis:
        parser.error("--case-id and --diagnosis are required unless using --all")

    case = load_case(args.case, args.case_id)

    with open(args.diagnosis, encoding="utf-8") as file:
        diagnosis = json.load(file)

    print(f"\nNetSage AI Rule Checker — Case {args.case_id}")
    print(f"Expected fault: {case['expected_fault']}")
    print(f"AI root cause: {diagnosis.get('root_cause', 'Not provided')}\n")

    diagnosis_results = check_diagnosis(
        diagnosis,
        case.get("show_command_output", "")
    )

    agrees, overlap_words = check_agreement(diagnosis, case.get("expected_fault", ""))
    add_result(
        diagnosis_results,
        "agrees_with_expected_fault",
        agrees,
        f"Matched keywords: {overlap_words}" if agrees else "No keyword overlap with expected fault"
    )

    failures = print_results(diagnosis_results)

    if args.network_config:
        with open(args.network_config, encoding="utf-8") as file:
            network_config = json.load(file)

        print("\nNetwork configuration checks:")
        network_results = check_network_config(network_config)
        failures += print_results(network_results)

    print(f"\nResult: {'PASS' if failures == 0 else 'FAIL'}")
    print("Human review is required before applying any fix.")

    sys.exit(0 if failures == 0 else 1)


if __name__ == "__main__":
    main()