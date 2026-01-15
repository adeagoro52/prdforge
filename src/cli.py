"""
PRDForge CLI - Minimal CLI for server management

Usage:
    prdforge serve     Start the web dashboard server
    prdforge init      Initialize a project configuration
    prdforge version   Show version information
"""

import sys


def main():
    """Entry point for PRDForge CLI."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    command = sys.argv[1]

    if command == "version":
        print("PRDForge v0.1.0 (not yet implemented)")
    elif command == "serve":
        print("Server not yet implemented. See Phase 2 of the PRD.")
    elif command == "init":
        print("Init not yet implemented. See Phase 1, task-006 of the PRD.")
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
