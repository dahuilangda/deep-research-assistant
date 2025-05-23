import os
import uuid

import logging
import time
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from deep_research import DeepSearch, QAnythingHandler
from openai_llm import OpenAI
import log

from dotenv import load_dotenv
load_dotenv()

# --- Environment Variable Setup ---
os.environ['OPENAI_API_KEY'] = os.getenv('OPENAI_API_KEY')
os.environ['OPENAI_BASE_URL'] = os.getenv('OPENAI_BASE_URL')
os.environ['OPENAI_MODEL_NAME'] = os.getenv('OPENAI_MODEL_NAME')

# Backend API URL
BACKEND_HOST = os.getenv('BACKEND_HOST')
BACKEND_PORT = int(os.getenv('BACKEND_PORT'))

# QAnything specific
QANYTHING_SERVER_URL = os.getenv("QANYTHING_SERVER_URL")
QANYTHING_USER_ID = os.getenv("QANYTHING_USER_ID")

# Firecrawl specific
os.environ['FIRECRAWL_API_URL'] = os.getenv('FIRECRAWL_API_URL')
os.environ['FIRECRAWL_API_KEY'] = os.getenv('FIRECRAWL_API_KEY')

# Suppress unnecessary logging from underlying libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
# logging.getLogger("openai").setLevel(logging.WARNING)

app = FastAPI()
job_results: Dict[str, Dict[str, Any]] = {}  # Stores job status, results, errors

# --- Global Handlers ---
# LLM can typically be global
llm_instance = OpenAI(model=os.getenv("OPENAI_MODEL_NAME"))

# QAnythingHandler can also be global
qanything_handler_global = QAnythingHandler(
    server_url=QANYTHING_SERVER_URL,
    user_id=QANYTHING_USER_ID
)

@app.on_event("startup")
def startup():
    app.logger = logging.getLogger("uvicorn")
    log.color_print("<startup>FastAPI application starting up.</startup>")
    log.color_print(f"<startup_config>OPENAI_BASE_URL: {os.getenv('OPENAI_BASE_URL')}</startup_config>")
    log.color_print(f"<startup_config>OPENAI_MODEL_NAME: {os.getenv('OPENAI_MODEL_NAME')}</startup_config>")
    log.color_print(f"<startup_config>QANYTHING_SERVER_URL: {QANYTHING_SERVER_URL}</startup_config>")
    log.color_print(f"<startup_config>FIRECRAWL_API_URL: {os.getenv('FIRECRAWL_API_URL')}</startup_config>")

def create_qanything_kb_for_job(job_id: str) -> Optional[str]:
    """
    Creates a new QAnything Knowledge Base for a specific job.
    Returns the KB ID if successful, None otherwise.
    """
    kb_name = f"api_job_{job_id.replace('-', '_')}_{int(time.time())}"
    try:
        response = qanything_handler_global.create_knowledge_base(kb_name)
        if response.get("code") == 200 and response.get("data", {}).get("kb_id"):
            kb_id = response.get("data", {}).get("kb_id")
            log.color_print(f"<qanything_kb_create> Job {job_id}: Created QAnything KB '{kb_name}' with ID: {kb_id}</qanything_kb_create>\n")
            return kb_id
        else:
            log.color_print(f"<qanything_kb_error> Job {job_id}: Failed to create QAnything KB '{kb_name}'. Response: {response}</qanything_kb_error>\n")
            return None
    except Exception as e:
        log.color_print(f"<qanything_kb_exception> Job {job_id}: QAnything KB creation for '{kb_name}' failed: {e}</qanything_kb_exception>\n")
        return None

def cleanup_qanything_kb(kb_id: str):
    """
    Deletes a QAnything Knowledge Base.
    """
    if not kb_id:
        return
    try:
        log.color_print(f"<qanything_kb_cleanup> Attempting to delete QAnything KB ID: {kb_id}</qanything_kb_cleanup>\n")
        response = qanything_handler_global.delete_knowledge_base(kb_ids=[kb_id]) # Corrected from deep_research example test
        if response.get("code") == 200:
            log.color_print(f"<qanything_kb_cleanup_success> Successfully deleted QAnything KB ID: {kb_id}</qanything_kb_cleanup_success>\n")
        else:
            log.color_print(f"<qanything_kb_cleanup_error> Failed to delete QAnything KB ID: {kb_id}. Response: {response}</qanything_kb_cleanup_error>\n")
    except Exception as e:
        log.color_print(f"<qanything_kb_cleanup_exception> Error deleting QAnything KB ID {kb_id}: {e}</qanything_kb_cleanup_exception>\n")


# --- Pydantic Models ---
class FilesQuery(BaseModel):
    file_paths: List[str]
    question: str
    search_web_flag: bool = False # Explicit flag for web search

class WebsQuery(BaseModel):
    urls: List[str]
    question: str
    search_web_flag: bool = True # Explicit flag for web search, default to True for web queries

class SearchQuery(BaseModel):
    question: str

class CombinedQuery(BaseModel):
    file_paths: Optional[List[str]] = None
    urls: Optional[List[str]] = None
    question: str
    search_web_flag: bool = False # Explicit flag for web search, default to False for combined queries


# --- Background Task Processors ---
def run_deep_search_task(
    job_id: str,
    kb_id: str,
    original_query: str,
    files: Optional[List[str]] = None,
    urls: Optional[List[str]] = None,
    search_web_flag: bool = False, # Explicit flag for web search
    max_iter_val: int = int(os.getenv('MAX_ITER', 3)),
    max_q_rerank: int = int(os.getenv("MAX_QANYTHING_CHUNKS_TO_RERANK", 5)),
    max_fc_qa_proc: int = int(os.getenv("MAX_FIRECRAWL_QANYTHING_CHUNKS_TO_PROCESS", 5)),
    min_qa_web: int = int(os.getenv("MIN_QANYTHING_RESULTS_BEFORE_WEB_SEARCH", 1)),
    max_web_search_results: int = int(os.getenv("MAX_WEB_SEARCH_RESULTS", 5)),
    max_summary_chunks: int = int(os.getenv("MAX_CHUNKS_FOR_SUMMARY", 20))
):
    job_results[job_id]["status"] = "processing"
    try:
        log.color_print(f"<job_start> Job {job_id} (KB: {kb_id}): Starting DeepSearch for query: '{original_query}'</job_start>\n")
        log.color_print(f"<job_params> Job {job_id}: files={files}, urls={urls}, search_web={search_web_flag}</job_params>\n")

        agent = DeepSearch(
            llm=llm_instance,
            qanything_handler=qanything_handler_global,
            qanything_kb_ids=[kb_id] if kb_id else [], # Must be a list
            max_iter=max_iter_val,
            search_internet=False, # Agent's default, will be overridden by query's search_web if needed
            firecrawl_api_url=os.getenv('FIRECRAWL_API_URL'),
            max_qanything_chunks_to_rerank=max_q_rerank,
            max_firecrawl_qanything_chunks_to_process=max_fc_qa_proc,
            min_qanything_results_before_web_search=min_qa_web,
            max_chunks_for_summary=max_summary_chunks
        )

        # The search_web parameter in agent.query() overrides the agent's instance search_internet default
        final_report, retrieved_docs, consumed_tokens = agent.query(
            original_query,
            files=files if files else [], # Ensure it's a list
            urls=urls if urls else [],   # Ensure it's a list
            search_web=search_web_flag,  # This controls if web search is performed
            max_web_search_results=max_web_search_results,
            # qanything_upload_num_split_pdf=0, # Default
            # qanything_upload_chunk_size=800   # Default
        )
        
        # Convert RetrievalResult objects to dicts if they are not directly JSON serializable
        serializable_docs = []
        for doc in retrieved_docs:
            serializable_docs.append({
                "text": doc.text,
                "reference": doc.reference,
                "metadata": doc.metadata,
                "score": doc.score,
            })

        job_results[job_id].update({
            "status": "completed",
            "result": {"answer": final_report, "retrieved_results": serializable_docs, "consumed_tokens": consumed_tokens},
            "error": None
        })
        log.color_print(f"<job_complete> Job {job_id} (KB: {kb_id}): DeepSearch completed.</job_complete>\n")

    except Exception as e:
        log.color_print(f"<job_error> Job {job_id} (KB: {kb_id}): Error during DeepSearch: {e}</job_error>\n")
        import traceback
        traceback.print_exc() # For detailed logs
        job_results[job_id].update({
            "status": "failed",
            "result": None,
            "error": str(e)
        })
    finally:
        if kb_id:
             log.color_print(f"<job_cleanup_info> Job {job_id}: KB {kb_id} cleanup is currently commented out. Consider manual cleanup or uncommenting cleanup_qanything_kb.</job_cleanup_info>\n")


# --- API Endpoints ---
@app.post("/api/files")
async def deepsearch_files_async(query_data: FilesQuery, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    kb_id = create_qanything_kb_for_job(job_id)
    if not kb_id:
        raise HTTPException(status_code=500, detail="Failed to create QAnything Knowledge Base for the job.")

    job_results[job_id] = {"status": "pending", "result": None, "error": None, "timestamp": time.time(), "kb_id": kb_id}
    background_tasks.add_task(
        run_deep_search_task,
        job_id,
        kb_id,
        query_data.question,
        files=query_data.file_paths,
        search_web_flag=query_data.search_web_flag # This flag is now part of the query data
    )
    return {"job_id": job_id, "message": "File processing job started."}

@app.post("/api/webs")
async def deepsearch_webs_async(query_data: WebsQuery, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    kb_id = create_qanything_kb_for_job(job_id)
    if not kb_id:
        raise HTTPException(status_code=500, detail="Failed to create QAnything Knowledge Base for the job.")

    job_results[job_id] = {"status": "pending", "result": None, "error": None, "timestamp": time.time(), "kb_id": kb_id}
    background_tasks.add_task(
        run_deep_search_task,
        job_id,
        kb_id,
        query_data.question,
        urls=query_data.urls,
        search_web_flag=query_data.search_web_flag
    )
    return {"job_id": job_id, "message": "Web content processing job started."}

@app.post("/api/search")
async def deepsearch_search_async(query_data: SearchQuery, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    # For pure web search, a KB might still be needed by DeepSearch to store crawled content before summarization.
    kb_id = create_qanything_kb_for_job(job_id)
    if not kb_id: # If KB creation is mandatory even for web-only search by DeepSearch
        raise HTTPException(status_code=500, detail="Failed to create QAnything Knowledge Base for the search job.")
    
    job_results[job_id] = {"status": "pending", "result": None, "error": None, "timestamp": time.time(), "kb_id": kb_id}
    log.color_print(f"<api_search> Job {job_id}: Received search request for: '{query_data.question}'</api_search>\n")

    background_tasks.add_task(
        run_deep_search_task,
        job_id,
        kb_id,
        query_data.question,
        search_web_flag=True # Perform web search
    )
    return {"job_id": job_id, "message": "Web search and analysis job started."}

@app.post("/api/combine")
async def deepsearch_combine_async(query_data: CombinedQuery, background_tasks: BackgroundTasks):
    job_id = str(uuid.uuid4())
    kb_id = create_qanything_kb_for_job(job_id)
    if not kb_id:
        raise HTTPException(status_code=500, detail="Failed to create QAnything Knowledge Base for the job.")

    job_results[job_id] = {"status": "pending", "result": None, "error": None, "timestamp": time.time(), "kb_id": kb_id}

    background_tasks.add_task(
        run_deep_search_task,
        job_id,
        kb_id,
        query_data.question,
        files=query_data.file_paths,
        urls=query_data.urls,
        search_web_flag=query_data.search_web_flag
    )
    return {"job_id": job_id, "message": "Combined processing job started."}

@app.get("/api/job/{job_id}")
async def get_job_status(job_id: str):
    if job_id not in job_results:
        raise HTTPException(status_code=404, detail="Job not found")
    return job_results[job_id]

@app.get("/api/cleanup")
def cleanup_stale_jobs(timeout_seconds: int = 1800): # Default timeout 30 minutes
    now = time.time()
    cleaned_jobs_count = 0
    freed_kbs = []

    for job_id, job_data in list(job_results.items()):
        is_stale_processing = job_data["status"] == "processing" and (now - job_data.get("timestamp", now)) > timeout_seconds
        is_old_completed = job_data["status"] in ["completed", "failed"] and (now - job_data.get("timestamp", now)) > (timeout_seconds * 10) # Clean very old completed jobs

        if is_stale_processing:
            job_results[job_id]["status"] = "failed"
            job_results[job_id]["error"] = "Timeout: Task took too long and was marked as stale."
            log.color_print(f"<job_cleanup_stale> Job {job_id} was stale (processing > {timeout_seconds}s), marked as failed.</job_cleanup_stale>\n")
            cleaned_jobs_count += 1
            
            # Try to clean up the KB if it exists
            kb_to_clean = job_data.get("kb_id")
            if kb_to_clean:
                cleanup_qanything_kb(kb_to_clean)
                freed_kbs.append(kb_to_clean)

        elif is_old_completed:
            log.color_print(f"<job_cleanup_old> Job {job_id} ({job_data['status']}) is old, removing from tracking. KB {job_data.get('kb_id')} might need manual cleanup if not done by task.</job_cleanup_old>\n")

            del job_results[job_id]
            cleaned_jobs_count += 1
            
    return {"cleaned_jobs_count": cleaned_jobs_count, "message": f"{cleaned_jobs_count} jobs processed for cleanup.", "potentially_freed_kbs": list(set(freed_kbs))}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=BACKEND_HOST, port=BACKEND_PORT, log_level="info")