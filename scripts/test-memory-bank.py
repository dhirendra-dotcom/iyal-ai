#!/usr/bin/env python3
"""Write and/or retrieve a harmless Memory Bank fact for one exact IYAL scope."""
from __future__ import annotations

import argparse
import agentplatform


def _memory_bank_name(project: str, location: str, value: str) -> str:
    if value.startswith("projects/"):
        return value
    # Memory Bank currently uses the reasoningEngines resource-name shape even
    # when provisioned as a standalone memory bank.
    return f"projects/{project}/locations/{location}/reasoningEngines/{value}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", required=True)
    parser.add_argument("--memory-bank-id", required=True)
    parser.add_argument("--user-id", default="iyal-memory-smoke-test")
    parser.add_argument("--app-name", default="arthistics")
    parser.add_argument(
        "--fact",
        default="I prefer an oval grip profile for adaptive utensil prototypes.",
    )
    parser.add_argument("--list-only", action="store_true")
    args = parser.parse_args()

    name = _memory_bank_name(args.project, args.location, args.memory_bank_id)
    scope = {"user_id": args.user_id, "app_name": args.app_name}
    client = agentplatform.Client(project=args.project, location=args.location)

    if not args.list_only:
        print(f"Writing test memory to: {name}")
        print(f"Scope: {scope}")
        operation = client.memory_banks.memories.generate(
            name=name,
            direct_memories_source={"direct_memories": [{"fact": args.fact}]},
            scope=scope,
            config={"wait_for_completion": True},
        )
        print("GenerateMemories completed:")
        print(operation)

    print("\nRetrieving memories for the exact same scope...")
    results = client.memory_banks.memories.retrieve(name=name, scope=scope)
    page = list(getattr(results, "page", []) or [])
    if not page:
        print("No memories found for this exact scope.")
        return

    print(f"Found {len(page)} memory item(s):")
    for item in page:
        memory = getattr(item, "memory", item)
        print(f"- {getattr(memory, 'fact', memory)}")


if __name__ == "__main__":
    main()
