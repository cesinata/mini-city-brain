"""Print the five-line summary and the local URLs after `make demo`.

Usage: python -m scripts.demo_summary <replay-summary.json> <pipeline-output.txt>
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from services.common.aws import s3_client
from services.common.config import Settings


def main(replay_json: str, pipeline_txt: str) -> int:
    text = Path(replay_json).read_text()
    summary = json.loads(text[text.index('{\n  "summary"') :])["summary"]
    settings = Settings.from_env()
    listing = s3_client(settings).list_objects_v2(Bucket=settings.raw_bucket, Prefix="raw/scats/")
    objects = listing.get("KeyCount", 0)
    out = Path(pipeline_txt).read_text()
    checks = next(
        (ln for ln in out.splitlines() if ln.startswith("PIPELINE")), "PIPELINE: no result"
    )
    print("")
    print("Summary")
    print(f"  1. readings sent:       {summary['readings_sent']}")
    print(f"  2. readings accepted:   {summary['accepted']}")
    print(f"  3. readings rejected:   {summary['rejected']}  {summary['reject_reasons'] or ''}")
    print(f"  4. objects written:     {objects} (raw/scats/ in the raw bucket)")
    print(f"  5. pipeline:            {checks}")
    print("")
    print("URLs")
    print("  API docs:   http://localhost:8000/docs")
    print("  Grafana:    http://localhost:3000   (anonymous viewer, dashboard 'mini-city-brain')")
    print("  Dagster UI: run `make dagster-ui`, then open http://localhost:3001")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
