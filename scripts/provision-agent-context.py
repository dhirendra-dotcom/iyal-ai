#!/usr/bin/env python3
"""Create the managed Sessions runtime and standalone Memory Bank once.

Usage:
  python scripts/provision-agent-context.py --project PROJECT_ID --location asia-south1

The script creates cloud resources; run it intentionally with an identity that has
roles/aiplatform.user (or equivalent permissions). IYAL itself remains on Cloud Run.
"""
from __future__ import annotations

import argparse

import agentplatform


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", required=True)
    parser.add_argument("--runtime-display-name", default="iyal-cloud-run-sessions")
    parser.add_argument("--memory-display-name", default="iyal-cloud-run-memory")
    args = parser.parse_args()

    client = agentplatform.Client(project=args.project, location=args.location)
    runtime = client.runtimes.create(config={"display_name": args.runtime_display_name})
    memory_bank = client.memory_banks.create(config={"display_name": args.memory_display_name})

    runtime_name = runtime.api_resource.name
    memory_name = memory_bank.name
    print("Created IYAL managed context resources:\n")
    print(f"AGENT_PLATFORM_LOCATION={args.location}")
    print(f"VERTEX_SESSION_RUNTIME_ID={runtime_name.split('/')[-1]}")
    print(f"VERTEX_MEMORY_BANK_ID={memory_name.split('/')[-1]}")
    print("MEMORY_ENABLED=true")
    print("\nFull resources:")
    print(f"Sessions runtime: {runtime_name}")
    print(f"Memory Bank:      {memory_name}")


if __name__ == "__main__":
    main()
