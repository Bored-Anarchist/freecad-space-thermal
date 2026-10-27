# SPDX-License-Identifier: MIT OR Apache-2.0
import argparse
import json
from fcst_app import capabilities


def main() -> int:
    parser = argparse.ArgumentParser(description="FCST application skeleton")
    parser.add_argument("--capabilities", action="store_true", required=True)
    parser.parse_args()
    print(json.dumps(capabilities(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
