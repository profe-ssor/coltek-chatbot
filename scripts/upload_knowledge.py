"""Upload knowledge/*.md to an OpenAI vector store, with a 'domain' attribute per file (notebook 03).

Usage (from the project root):
    python scripts/upload_knowledge.py                          # new vector store with every file; prints its ID for .env
    python scripts/upload_knowledge.py --list                   # show the files in the store from .env and their domains
    python scripts/upload_knowledge.py --replace faqs.md        # upload a new version of one file, then delete the old copy

--list and --replace use VECTOR_STORE_ID from .env unless you pass --vector-store-id.
The domain labels must match the filters in chatbot/agents/common.py.
"""
import argparse
import sys
from pathlib import Path

# Make `import chatbot` work when the script is run as `python scripts/upload_knowledge.py`
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from openai import OpenAI  # noqa: E402

from chatbot.config import settings  # noqa: E402  (also puts OPENAI_API_KEY in the environment)

KNOWLEDGE_DIR = PROJECT_ROOT / "knowledge"


def get_domain(filename: str) -> str:
    """The 'domain' label for a knowledge file. The agents' file search filters on these."""
    name = filename.lower()
    if "service" in name or "portfolio" in name:
        return "services"   # portfolio = past projects, useful for sales
    if "academy" in name:
        return "academy"
    if "opendoor" in name:
        return "opendoor"
    return "company"        # company.md, faqs.md, contact_and_socials.md are shared by everyone


def upload_file(client: OpenAI, vector_store_id: str, path: Path):
    """Upload one file with its domain attribute and wait until it is indexed."""
    domain = get_domain(path.name)
    with open(path, "rb") as f:
        vs_file = client.vector_stores.files.upload_and_poll(
            vector_store_id=vector_store_id,
            file=f,
            attributes={"domain": domain},
        )
    print(f"Uploaded {path.name} | domain={domain} | status={vs_file.status} | id={vs_file.id}")
    return vs_file


def files_in_store(client: OpenAI, vector_store_id: str) -> list[tuple[str, str, dict]]:
    """(file_id, filename, attributes) for every file in the vector store."""
    rows = []
    for vs_file in client.vector_stores.files.list(vector_store_id=vector_store_id):
        filename = client.files.retrieve(vs_file.id).filename
        rows.append((vs_file.id, filename, vs_file.attributes or {}))
    return rows


def upload_all(client: OpenAI) -> None:
    md_files = sorted(KNOWLEDGE_DIR.glob("*.md"))
    if not md_files:
        sys.exit(f"No .md files found in {KNOWLEDGE_DIR}")
    print(f"Found {len(md_files)} files in {KNOWLEDGE_DIR}")

    vector_store = client.vector_stores.create(name="coltek-knowledge")
    for path in md_files:
        upload_file(client, vector_store.id, path)

    print(f"\nVECTOR_STORE_ID={vector_store.id}  <- put this in your .env")


def list_store(client: OpenAI, vector_store_id: str) -> None:
    rows = files_in_store(client, vector_store_id)
    print(f"{len(rows)} files in {vector_store_id}")
    for file_id, filename, attributes in rows:
        print(f"  {filename:28} domain={attributes.get('domain')} | id={file_id}")


def replace_file(client: OpenAI, vector_store_id: str, filename: str) -> None:
    path = KNOWLEDGE_DIR / filename
    if not path.is_file():
        sys.exit(f"Not found: {path}")

    # 1. Find the old copies first
    old_ids = [file_id for file_id, name, _ in files_in_store(client, vector_store_id) if name == filename]

    # 2. Upload the new version (before deleting, so the store is never missing the file)
    new_file = upload_file(client, vector_store_id, path)
    if new_file.status != "completed":
        sys.exit(f"Upload status is {new_file.status}; old copies were NOT deleted: {old_ids}")

    # 3. Delete the old copies from the store and from file storage
    for file_id in old_ids:
        client.vector_stores.files.delete(file_id, vector_store_id=vector_store_id)
        client.files.delete(file_id)
        print(f"Deleted old copy {file_id}")
    if not old_ids:
        print("No old copy was in the store (the file was simply added).")


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload the Coltek knowledge files to an OpenAI vector store.")
    parser.add_argument("--replace", metavar="FILENAME", help="replace one file, e.g. faqs.md")
    parser.add_argument("--list", action="store_true", help="list the files in the vector store")
    parser.add_argument("--vector-store-id", default=settings.vector_store_id,
                        help="vector store to use for --list/--replace (default: VECTOR_STORE_ID from .env)")
    args = parser.parse_args()

    client = OpenAI()

    if args.list or args.replace:
        if not args.vector_store_id:
            sys.exit("No vector store ID: set VECTOR_STORE_ID in .env or pass --vector-store-id")
        if args.replace:
            replace_file(client, args.vector_store_id, args.replace)
        if args.list:
            list_store(client, args.vector_store_id)
    else:
        upload_all(client)


if __name__ == "__main__":
    main()
