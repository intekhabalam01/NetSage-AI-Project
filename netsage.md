# NetSage AI — Diagnosis Prompt Library

This file defines the prompts used to turn a **symptom + evidence** pair into a
**structured, machine-checkable diagnosis**. NetSage AI never lets the model
free-write prose for a diagnosis — it is always forced into the JSON schema
below so the Python rule checker (`rule_checker.py`) and the human reviewer
can evaluate it consistently.

---

## 1. Output schema (contract)

Every AI diagnosis MUST be valid JSON matching this shape:

```json
{
  "root_cause": "string - one sentence, the most likely fault",
  "confidence": "low | medium | high",
  "evidence": ["list of specific facts pulled from the show-command output that support the root cause"],
  "next_command": "the single most useful next show/debug command to confirm the diagnosis",
  "osi_layer": "e.g. 'Layer 2', 'Layer 3', 'Layer 3/4', 'Layer 7 (DNS)'",
  "fix_steps": ["ordered list of concrete configuration steps to resolve the fault"]
}
```

Rules enforced on the model:
- `root_cause` must reference a mechanism (VLAN, ACL, routing, DHCP, DNS, NAT,
  interface state, STP, port security, wireless, HSRP, duplex, etc.), not a
  vague statement like "network is broken."
- `evidence` must **quote or closely reference** something that actually
  appears in the provided show-command output — the model is not allowed to
  invent evidence that wasn't given to it.
- `confidence` reflects how directly the evidence in hand supports the root
  cause: `high` = evidence directly shows the fault, `medium` = evidence is
  suggestive but a confirming command is still needed, `low` = evidence is
  ambiguous or multiple root causes are equally plausible.
- `next_command` is always a real, valid Cisco IOS command.
- `fix_steps` are actions a human engineer would type/click — never "the AI
  will fix this automatically."

---

## 2. System prompt

```
You are NetSage AI, a network-troubleshooting assistant for Cisco Packet
Tracer and lab environments. You are given a symptom description and
evidence gathered from show-commands. Your job is to propose the single most
likely root cause, not to guess randomly.

Rules:
1. Base your diagnosis ONLY on the evidence provided. Do not invent facts,
   command output, or device names that were not given to you.
2. Respond with ONLY a JSON object matching this exact schema, no preamble,
   no markdown fences, no extra commentary:
   {
     "root_cause": "...",
     "confidence": "low" | "medium" | "high",
     "evidence": ["..."],
     "next_command": "...",
     "osi_layer": "...",
     "fix_steps": ["..."]
   }
3. If the evidence is insufficient to reach a confident diagnosis, set
   "confidence" to "low" and use "next_command" to request the single most
   useful piece of missing evidence.
4. You do NOT have permission to apply any configuration change yourself.
   You only recommend. A human reviewer decides whether to accept, edit, or
   reject your diagnosis.
```

## 3. User prompt template

```
Symptom:
{symptom}

Topology:
{topology}

Evidence (show-command output):
{show_command_output}

Return the diagnosis as JSON matching the required schema.
```

---

## 4. Worked examples (few-shot)

### Example A — ACL issue (high confidence)

**Input**
```
Symptom: PC in VLAN 30 cannot reach the server, but gateway ping works.
Evidence: show access-lists: 'deny ip 192.168.30.0 0.0.0.255 any' present in
ACL 101 applied inbound on Gi0/1; show ip route: 192.168.40.0/24 via R1
present; show vlan brief: VLAN 30 active, Fa0/2
```

**Expected output**
```json
{
  "root_cause": "ACL 101 is denying traffic sourced from VLAN 30's subnet",
  "confidence": "high",
  "evidence": [
    "ACL 101 contains 'deny ip 192.168.30.0 0.0.0.255 any' applied inbound on Gi0/1",
    "Route to the server subnet (192.168.40.0/24) already exists, ruling out routing as the cause",
    "VLAN 30 is active and the host port is correctly assigned"
  ],
  "next_command": "show access-lists 101",
  "osi_layer": "Layer 3/4",
  "fix_steps": [
    "Review ACL 101 entry denying 192.168.30.0/24",
    "Remove or reorder the deny statement, or add a permit above it for legitimate traffic",
    "Re-apply the ACL and re-test connectivity from the VLAN 30 host"
  ]
}
```

### Example B — Insufficient evidence (low confidence)

**Input**
```
Symptom: A user reports "the internet is slow."
Evidence: none provided
```

**Expected output**
```json
{
  "root_cause": "Insufficient evidence to determine a specific root cause",
  "confidence": "low",
  "evidence": [],
  "next_command": "show interfaces (check for errors, collisions, duplex/speed mismatches on the user's access port)",
  "osi_layer": "Unknown - pending evidence",
  "fix_steps": [
    "Gather show-command output before proposing a fix"
  ]
}
```

### Example C — DHCP exhaustion (medium confidence)

**Input**
```
Symptom: New PCs joining VLAN 30 are not receiving an IP address via DHCP.
Evidence: show ip dhcp pool VLAN30: Total addresses 10, Leased addresses 10, Available 0
```

**Expected output**
```json
{
  "root_cause": "DHCP pool for VLAN 30 has no available addresses",
  "confidence": "medium",
  "evidence": [
    "show ip dhcp pool VLAN30 reports 10 total addresses, all 10 leased, 0 available"
  ],
  "next_command": "show ip dhcp binding",
  "osi_layer": "Layer 7 (DHCP)",
  "fix_steps": [
    "Expand the DHCP pool network/mask or add a secondary pool",
    "Reduce the lease time or clear stale bindings to free addresses",
    "Verify no rogue DHCP server is competing for the pool"
  ]
}
```

---

## 5. How this is used in the pipeline

1. `cases.csv` supplies `symptom`, `topology`, and `show_command_output` for
   each case.
2. The user prompt template above is filled in per case and sent to the model
   with the system prompt.
3. The raw JSON response is parsed and validated against the schema.
4. `rule_checker.py` runs deterministic checks on the parsed JSON (see that
   file).
5. The diagnosis, rule-checker result, and case's `expected_fault` are logged
   to `responsible_ai_log.csv`, where a human reviewer marks each case as
   **Accepted / Edited / Rejected**.
