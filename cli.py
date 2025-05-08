#!/usr/bin/env python3
import os
import argparse
from dotenv import load_dotenv
import log
from openai_llm import OpenAI
from qanything_utils import QAnythingHandler
from deep_research import DeepSearch

def setup_agent():
    """Initialize DeepSearch agent with environment variables."""
    load_dotenv()
    llm = OpenAI(model=os.getenv("OPENAI_MODEL_NAME"))
    qhandler = QAnythingHandler(
        server_url=os.getenv("QANYTHING_SERVER_URL"),
        user_id=os.getenv("QANYTHING_USER_ID")
    )

    kb_id = None
    try:
        resp = qhandler.create_knowledge_base(f"deep_search_cli_kb_{os.getpid()}")
        data = resp.get("data", {})
        if resp.get("code") == 200 and data.get("kb_id"):
            kb_id = data["kb_id"]
            log.color_print(f"<setup>Created KB ID {kb_id}</setup>")
    except Exception:
        pass
    if not kb_id:
        kbs = qhandler.list_knowledge_bases().get("data", [])
        if kbs:
            kb_id = kbs[0].get("kb_id")
            log.color_print(f"<setup_warn>Using existing KB ID {kb_id}</setup_warn>")

    agent = DeepSearch(
        llm=llm,
        qanything_handler=qhandler,
        qanything_kb_ids=[kb_id] if kb_id else [],
        firecrawl_api_url=os.getenv("FIRECRAWL_API_URL")
    )
    return agent


def main():
    parser = argparse.ArgumentParser(
        description="Command-line interface for DeepSearch agent"
    )
    parser.add_argument(
        "query",
        help="The query string to search and summarize"
    )
    parser.add_argument(
        "-f", "--file",
        dest="files",
        action="append",
        help="Local file(s) to upload and search (PDF/MD/etc). Can be used multiple times."
    )
    parser.add_argument(
        "-u", "--url",
        dest="urls",
        action="append",
        help="URL(s) to scrape and search. Can be used multiple times."
    )
    parser.add_argument(
        "-w", "--search-web",
        dest="search_web",
        action="store_true",
        help="Enable conditional web search via Firecrawl"
    )
    parser.add_argument(
        "--chunk-size",
        dest="chunk_size",
        type=int,
        default=800,
        help="Chunk size for QAnything uploads"
    )
    parser.add_argument(
        "--max-iter",
        dest="max_iter",
        type=int,
        default=3,
        help="Maximum number of search iterations"
    )
    parser.add_argument(
        "--max-chunks",
        dest="max_chunks",
        type=int,
        default=20,
        help="Maximum number of chunks for summary"
    )
    args = parser.parse_args()

    agent = setup_agent()
    # prepare kwargs
    kwargs = {
        "files": args.files,
        "urls": args.urls,
        "search_web": args.search_web,
        "max_iter": args.max_iter,
        "max_chunks_for_summary": args.max_chunks,
    }

    answer, docs, tokens = agent.query(args.query, **kwargs)

    print("\n=== Answer ===")
    print(answer)
    print(f"\nRetrieved {len(docs)} documents, consumed {tokens} tokens.")

if __name__ == '__main__':
    main()
