import json
import sys

path = r'C:\Users\EliteBook\.gemini\antigravity-ide\brain\6d60d643-371c-47ad-b140-026ef1aa1f5c\.system_generated\logs\transcript.jsonl'
with open(path, 'r', encoding='utf-8') as f:
    lines = [json.loads(line) for line in f]

with open('scratch/last_steps.txt', 'w', encoding='utf-8') as out:
    out.write(f"Total entries: {len(lines)}\n")
    for i in range(300, len(lines)):
        entry = lines[i]
        out.write(f"\n--- Entry {i} ({entry.get('source')}, {entry.get('type')}) ---\n")
        if entry.get("content"):
            out.write(f"Content: {entry.get('content')}\n")
        if entry.get("tool_calls"):
            for t in entry.get("tool_calls"):
                out.write(f"Tool call: {t.get('name')}\nArgs: {t.get('args')}\n")

print("Wrote scratch/last_steps.txt")
