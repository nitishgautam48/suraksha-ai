"""Index the knowledge base from the command line.

python scripts/ingest_knowledge.py            # bundled + uploaded + fetched documents
python scripts/ingest_knowledge.py --fetch    # download rag/sources.json entries first
python scripts/ingest_knowledge.py DIR        # index every .pdf/.md/.txt/.html file in DIR
"""

import argparse
from pathlib import Path

from backend.database.session import session_scope
from backend.rag.ingest import ingest_directory
from backend.services.knowledge_service import fetch_and_ingest
from backend.utils.logging import configure_logging

configure_logging()
parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("directory", nargs="?", type=Path)
parser.add_argument("--fetch", action="store_true", help="download the official sources in rag/sources.json")
args = parser.parse_args()

if args.fetch:
    with session_scope() as db:
        for r in fetch_and_ingest(db):
            print(f"{r['status']:>8}  {r['chunks']:>4} chunks  {r['url']}  {r['error'] or ''}")
result = ingest_directory(args.directory)
ok = {k: v for k, v in result.items() if v >= 0}
print(f"Indexed {sum(ok.values())} chunks from {len(ok)} documents; {len(result) - len(ok)} failed")
