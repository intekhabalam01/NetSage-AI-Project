import csv
import json
import os
import time
from google import genai
from dotenv import load_dotenv

load_dotenv()

API_KEYS = [
    os.environ.get("GEMINI_API_KEY_1"),
    os.environ.get("GEMINI_API_KEY_2"),
    os.environ.get("GEMINI_API_KEY_3"),
]

cases_file = "cases.csv"
diagnoses_file = "ai_diagnoses.json"

ai_diagnoses = []
existing_ids = set()

if os.path.exists(diagnoses_file):
    try:
        with open(diagnoses_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                ai_diagnoses = data
            elif isinstance(data, dict):
                ai_diagnoses = [data]
            existing_ids = {d.get("case_id") for d in ai_diagnoses if isinstance(d, dict)}
    except Exception:
        ai_diagnoses = []

key_index = 0

def get_client(idx):
    return genai.Client(api_key=API_KEYS[idx])

client = get_client(key_index)

with open(cases_file, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        case_id = row["case_id"]

        if case_id in existing_ids:
            print(f"[{case_id}] Already saved, skipping.")
            continue

        print(f"[{case_id}] Processing with Key {key_index + 1}...")

        prompt = f"""
        You are NetSage AI, a network troubleshooting assistant.
        Symptom: {row['symptom']}
        Topology: {row['topology']}
        Evidence: {row['show_command_output']}

        Respond ONLY with a valid JSON matching this exact structure:
        {{
          "case_id": "{case_id}",
          "root_cause": "...",
          "confidence": "high",
          "evidence": ["..."],
          "next_command": "...",
          "osi_layer": "{row['osi_layer']}",
          "fix_steps": ["..."]
        }}
        """

        success = False
        attempts = 0

        while not success and attempts < (len(API_KEYS) * 10):
            try:
                response = client.models.generate_content(
                    model="gemini-3.6-flash",
                    contents=prompt
                )

                raw_text = response.text.strip()
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]

                result = json.loads(raw_text.strip())
                ai_diagnoses.append(result)
                existing_ids.add(case_id)

                with open(diagnoses_file, "w", encoding="utf-8") as out_f:
                    json.dump(ai_diagnoses, out_f, indent=2)

                success = True
                print(f"  [SUCCESS] {case_id} completed.")
                time.sleep(5)

            except Exception as e:
                print(f"  Quota / Server Busy on Key {key_index + 1}. Waiting 15s...")
                key_index = (key_index + 1) % len(API_KEYS)
                client = get_client(key_index)
                attempts += 1
                time.sleep(15)

print(f"\nALL DONE! Total successful cases: {len(ai_diagnoses)}/30")