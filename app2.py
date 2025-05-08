import requests
import time
import os
import re

import streamlit as st
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

BACKEND_HOST = os.getenv("BACKEND_HOST")
BACKEND_PORT = os.getenv("BACKEND_PORT")
API_BASE = f"http://{BACKEND_HOST}:{BACKEND_PORT}"

# Local temporary file storage directory
FILE_PATH = os.getenv('TMP_FILE_PATH')

# Streamlit page configuration
st.set_page_config(page_title="Deep Research Assistant", layout="centered")
st.title("🔍 Deep Research Assistant")

# Query type selection
query_type = st.radio(
    "Choose query mode:",
    ["Upload Files", "Enter URLs", "Web Search", "Combined Query"],
    key="query_type_radio"
)

# Question input area
question = st.text_area(
    "Enter your question:",
    placeholder="e.g.: What is the research objective of this article?",
    height=100,
    key="question_text_area"
)

# Initialize variables
uploaded_files = None
urls_input = ""
search_web_flag = False

# Display inputs based on query type
if query_type == "Upload Files":
    uploaded_files = st.file_uploader("Select file(s)", accept_multiple_files=True, key="file_uploader_files")
    search_web_flag = st.checkbox("Supplement with web search", key="web_complement_files")
elif query_type == "Enter URLs":
    urls_input = st.text_area("Enter URL(s) (one per line)", height=100, key="url_input_webs")
    search_web_flag = st.checkbox("Supplement with web search", key="web_complement_webs")
elif query_type == "Web Search":
    st.info("This mode will search the web directly for answers.")
elif query_type == "Combined Query":
    uploaded_files = st.file_uploader("Select file(s) (optional)", accept_multiple_files=True, key="file_uploader_combined")
    urls_input = st.text_area("Enter URL(s) (optional, one per line)", height=100, key="url_input_combined")
    search_web_flag = st.checkbox("Supplement with web search", key="web_complement_combined")

# Submit button
submit_button = st.button("🚀 Start Analysis", key="submit_button_main")

if submit_button:
    if not question.strip():
        st.warning("Please enter your question.")
        st.stop()

    payload = {"question": question}
    api_endpoint = None
    job_started_message = ""
    processed_file_paths = []

    if query_type == "Upload Files":
        if not uploaded_files:
            st.warning("Please upload at least one file.")
            st.stop()
        file_paths = []
        for f in uploaded_files:
            filepath = os.path.join(FILE_PATH, f.name)
            try:
                with open(filepath, "wb") as out_file:
                    out_file.write(f.read())
                file_paths.append(filepath)
                processed_file_paths.append(filepath)
            except Exception as e:
                st.error(f"Failed to save file {f.name}: {e}")
                st.stop()
        payload["file_paths"] = file_paths
        payload["search_web_flag"] = search_web_flag
        api_endpoint = f"{API_BASE}/api/files"
        job_started_message = "File processing task started."

    elif query_type == "Enter URLs":
        if not urls_input.strip():
            st.warning("Please enter at least one URL.")
            st.stop()
        url_list = [u.strip() for u in urls_input.splitlines() if u.strip()]
        payload["urls"] = url_list
        payload["search_web_flag"] = search_web_flag
        api_endpoint = f"{API_BASE}/api/webs"
        job_started_message = "Web content processing task started."

    elif query_type == "Web Search":
        api_endpoint = f"{API_BASE}/api/search"
        job_started_message = "Web search and analysis task started."

    elif query_type == "Combined Query":
        file_paths = []
        if uploaded_files:
            for f in uploaded_files:
                filepath = os.path.join(FILE_PATH, f.name)
                try:
                    with open(filepath, "wb") as out_file:
                        out_file.write(f.read())
                    file_paths.append(filepath)
                    processed_file_paths.append(filepath)
                except Exception as e:
                    st.error(f"Failed to save file {f.name}: {e}")
                    st.stop()
        url_list = [u.strip() for u in urls_input.splitlines() if u.strip()]
        if not file_paths and not url_list and not search_web_flag:
            st.warning("Please provide files, URLs, or enable web search.")
            st.stop()
        payload["file_paths"] = file_paths or None
        payload["urls"] = url_list or None
        payload["search_web_flag"] = search_web_flag
        api_endpoint = f"{API_BASE}/api/combine"
        job_started_message = "Combined processing task started."

    # Submit to backend and poll
    if api_endpoint:
        try:
            res = requests.post(api_endpoint, json=payload)
            res.raise_for_status()
            data = res.json()
            if "job_id" not in data:
                st.error(f"Invalid response: missing job_id. Response: {data}")
                st.stop()
            job_id = data["job_id"]
            st.success(f"Task submitted! Job ID: {job_id}. {job_started_message}")
        except Exception as e:
            st.error(f"Failed to submit task: {e}")
            st.stop()

        progress_bar = st.progress(0)
        status_area = st.empty()
        max_attempts = int(os.getenv("POLLING_ATTEMPTS", 240))
        interval = int(os.getenv("POLL_INTERVAL_SECONDS", 5))

        for i in range(max_attempts):
            try:
                status_res = requests.get(f"{API_BASE}/api/job/{job_id}")
                status_res.raise_for_status()
                job_data = status_res.json()
                progress_bar.progress((i+1)/max_attempts)

                status = job_data.get("status")
                if status == "completed":
                    status_area.success("✅ Analysis completed!")
                    answer = job_data["result"].get("answer", "No answer returned.")
                    # Remove any <think> tags
                    answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.DOTALL).strip()
                    st.markdown("### 📝 Analysis Result:")
                    st.markdown(answer, unsafe_allow_html=True)

                    refs = job_data["result"].get("retrieved_results", [])
                    if refs:
                        st.markdown("### 📚 References:")
                        for idx, ref in enumerate(refs, 1):
                            source = ref.get("reference", "Unknown source")
                            text = ref.get("text", "No content")
                            score = ref.get("score")
                            title = f"{idx}. {source[:60] + '...' if len(source)>60 else source}"
                            if score is not None:
                                title += f" (Score: {score:.2f})"
                            with st.expander(title):
                                st.caption(f"Source: {source}")
                                st.markdown(text[:1000] + ('...' if len(text)>1000 else ''), unsafe_allow_html=True)

                    st.markdown(f"---\n*Tokens used: {job_data['result'].get('consumed_tokens', 'Unknown')}*")

                    # Cleanup temp files
                    for path in processed_file_paths:
                        try:
                            if os.path.exists(path):
                                os.remove(path)
                        except Exception as e:
                            st.warning(f"Unable to delete temp file {path}: {e}")
                    break

                elif status == "failed":
                    status_area.error(f"❌ Analysis failed: {job_data.get('error', 'Unknown error')}")
                    break
                elif status in ("processing", "pending"):
                    status_area.info(f"⏳ Task {status}... (Attempt {i+1}/{max_attempts})")
                else:
                    status_area.warning(f"⚠️ Unknown status: {status} (Attempt {i+1}/{max_attempts})")

                time.sleep(interval)
            except Exception as e:
                status_area.error(f"Error during polling: {e}")
                time.sleep(10)
        else:
            status_area.warning("⏰ Analysis timed out. Please check backend logs or try again later.")
            st.info(f"You can check status later with Job ID: {job_id} at /api/job/{job_id}.")
