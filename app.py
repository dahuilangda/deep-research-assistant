import requests
import time
import os
import re

import streamlit as st

from dotenv import load_dotenv
load_dotenv()

BACKEND_HOST = os.getenv("BACKEND_HOST")
BACKEND_PORT = os.getenv("BACKEND_PORT")

API_BASE = f"http://{BACKEND_HOST}:{BACKEND_PORT}"

# 本地临时文件存储目录
FILE_PATH = os.getenv('TMP_FILE_PATH')

st.set_page_config(page_title="Deep Research 研究助手", layout="centered")
st.title("🔍 Deep Research 研究助手")

# 通过单选项让用户选择不同查询方式
query_type = st.radio(
    "请选择查询方式:",
    ["上传文件", "输入网址", "网络搜索", "组合查询"],
    key="query_type_radio"
)

# 输入问题（文本区域）
question = st.text_area(
    "请输入你的问题：",
    placeholder="例如：这篇文章的研究目的是什么？",
    height=100,
    key="question_text_area"
)

# --- 根据选择的查询方式显示相应的输入控件 ---
uploaded_files = None
urls_input = "" # 修改变量名以避免与 url_list 冲突
search_web_flag = False # 用于补充文件/URL的联网搜索标志

if query_type == "上传文件":
    uploaded_files = st.file_uploader("选择文件", accept_multiple_files=True, key="file_uploader_files")
    search_web_flag = st.checkbox("联网补充资料 (从网络搜索信息以增强答案)", key="web_complement_files")
elif query_type == "输入网址":
    urls_input = st.text_area("请输入网址（可多个，每行一个）", height=100, key="url_input_webs")
    search_web_flag = st.checkbox("联网补充资料 (从网络搜索信息以增强答案)", key="web_complement_webs")
elif query_type == "网络搜索":
    st.info("此模式将直接在网络上搜索答案。")
    # 后端 /api/search 默认进行网络搜索，前端无需额外参数控制搜索行为本身
    # 如果需要如 "science" 或 "news" 的模式，后端 DeepSearch agent 需要支持此区分
elif query_type == "组合查询":
    uploaded_files = st.file_uploader("选择文件 (可选)", accept_multiple_files=True, key="file_uploader_combined")
    urls_input = st.text_area("请输入网址 (可选, 每行一个)", height=100, key="url_input_combined")
    search_web_flag = st.checkbox("联网补充资料 (若提供文件/网址则补充搜索；否则将进行网络搜索)", key="web_complement_combined")

# 提交按钮
submit_button = st.button("🚀 开始分析", key="submit_button_main")

if submit_button:
    if not question.strip():
        st.warning("请输入你的问题。")
        st.stop()

    payload = {"question": question}
    api_endpoint = ""
    job_started_message = ""
    processed_file_paths = [] # 用于跟踪本次上传的文件路径，以便后续清理

    # 根据查询类型准备数据
    if query_type == "上传文件":
        if not uploaded_files:
            st.warning("请上传至少一个文件。")
            st.stop()
        current_file_paths = []
        for f_upload in uploaded_files:
            # 使用唯一的临时文件名以避免冲突 (如果需要)
            # unique_filename = f"{uuid.uuid4().hex}_{f_upload.name}"
            # filepath = os.path.join(FILE_PATH, unique_filename)
            filepath = os.path.join(FILE_PATH, f_upload.name) # 保持原样，但注意同名文件覆盖
            try:
                with open(filepath, "wb") as out_file:
                    out_file.write(f_upload.read())
                current_file_paths.append(filepath)
                processed_file_paths.append(filepath)
                # print(f"DEBUG: Saved file {filepath}")
            except Exception as e:
                st.error(f"保存文件失败 {f_upload.name}: {e}")
                st.stop()
        payload["file_paths"] = current_file_paths
        payload["search_web_flag"] = search_web_flag
        api_endpoint = f"{API_BASE}/api/files"
        job_started_message = "文件处理任务已开始。"

    elif query_type == "输入网址":
        if not urls_input.strip():
            st.warning("请输入网址。")
            st.stop()
        url_list = [u.strip() for u in urls_input.splitlines() if u.strip()]
        if not url_list:
            st.warning("请输入有效的网址。")
            st.stop()
        payload["urls"] = url_list
        payload["search_web_flag"] = search_web_flag
        api_endpoint = f"{API_BASE}/api/webs"
        job_started_message = "网页内容处理任务已开始。"

    elif query_type == "网络搜索":
        api_endpoint = f"{API_BASE}/api/search"
        job_started_message = "网络搜索与分析任务已开始。"

    elif query_type == "组合查询":
        current_file_paths = []
        if uploaded_files:
            for f_upload in uploaded_files:
                filepath = os.path.join(FILE_PATH, f_upload.name)
                try:
                    with open(filepath, "wb") as out_file:
                        out_file.write(f_upload.read())
                    current_file_paths.append(filepath)
                    processed_file_paths.append(filepath)
                    # print(f"DEBUG: Saved file {filepath}")
                except Exception as e:
                    st.error(f"保存文件失败 {f_upload.name}: {e}")
                    st.stop()

        url_list = []
        if urls_input.strip():
            url_list = [u.strip() for u in urls_input.splitlines() if u.strip()]

        if not current_file_paths and not url_list and not search_web_flag:
            # 如果用户没有提供任何输入，并且没有勾选联网补充，提示他们
            st.warning("请至少提供文件、网址，或勾选“联网补充资料”以进行纯网络搜索。")
            st.stop()
        
        payload["file_paths"] = current_file_paths if current_file_paths else None
        payload["urls"] = url_list if url_list else None
        payload["search_web_flag"] = search_web_flag
        api_endpoint = f"{API_BASE}/api/combine"
        job_started_message = "组合处理任务已开始。"
    else:
        st.error("无效的查询类型。")
        st.stop()

    # --- 提交到后端并轮询结果 ---
    job_id = None
    if api_endpoint:
        with st.spinner("正在提交任务，请稍等..."):
            try:
                # print(f"DEBUG: Submitting to: {api_endpoint} with payload: {payload}")
                res = requests.post(api_endpoint, json=payload)
                res.raise_for_status()
                response_data = res.json()
                if "job_id" not in response_data:
                    st.error(f"任务提交响应错误：未找到 job_id。响应: {response_data}")
                    st.stop()
                job_id = response_data["job_id"]
                st.success(f"任务已提交！Job ID: {job_id}. {job_started_message}")
            except requests.exceptions.RequestException as e:
                st.error(f"提交任务失败：{e}")
                if e.response is not None:
                    st.error(f"后端响应: {e.response.status_code} - {e.response.text}")
                st.stop()
            except Exception as e:
                st.error(f"提交任务时发生未知错误: {e}")
                st.stop()

    if job_id:
        progress_bar = st.progress(0)
        status_text_area = st.empty() # 用于显示轮询状态的文本区域

        polling_attempts = int(os.getenv("POLLING_ATTEMPTS", 240))  # 最大轮询次数 (例如 240 * 5秒 = 20分钟)
        for i in range(polling_attempts):
            try:
                status_res = requests.get(f"{API_BASE}/api/job/{job_id}")
                status_res.raise_for_status()
                job_data = status_res.json()

                progress = (i + 1) / polling_attempts
                progress_bar.progress(min(progress, 1.0))

                if job_data["status"] == "completed":
                    status_text_area.success("✅ 分析完成！")
                    progress_bar.progress(1.0)

                    answer = job_data.get("result", {}).get("answer", "未能获取到答案。")
                    references = job_data.get("result", {}).get("retrieved_results", [])
                    consumed_tokens = job_data.get("result", {}).get("consumed_tokens", "未知")

                    # 清理答案中的 <think> 标签
                    if isinstance(answer, str) and "<think>" in answer and "</think>" in answer:
                        # 使用 re.split 来处理可能的多行 <think> 块或不规范的换行
                        parts = re.split(r'<think>.*?</think>\s*', answer, flags=re.DOTALL)
                        answer = parts[-1].strip()


                    st.markdown("### 📝 分析结果:")
                    st.markdown(answer, unsafe_allow_html=True)

                    if references:
                        st.markdown("### 📚 参考文献:")
                        for idx, ref in enumerate(references, start=1):
                            ref_text = ref.get('text', '无文本内容')
                            ref_source = ref.get('reference', '未知来源')
                            ref_score = ref.get('score', None)
                            display_source = ref_source
                            if len(ref_source) > 100: # 截断过长的来源以适应标题
                                display_source = ref_source[:97] + "..."
                            
                            expander_title = f"{idx}. {display_source}"
                            if ref_score is not None:
                                expander_title += f" (相关性: {ref_score:.2f})"

                            with st.expander(expander_title):
                                st.caption(f"来源: {ref_source}")
                                st.markdown(ref_text[:1000] + "..." if len(ref_text) > 1000 else ref_text, unsafe_allow_html=True)
                    
                    st.markdown(f"--- \n*Tokens 消耗: {consumed_tokens}*")
                    
                    # 清理本次任务上传的临时文件
                    if processed_file_paths:
                        # print(f"DEBUG: Attempting to clean files: {processed_file_paths}")
                        for p_path in processed_file_paths:
                            try:
                                if os.path.exists(p_path):
                                    os.remove(p_path)
                                    # print(f"DEBUG: Successfully removed temp file {p_path}")
                            except Exception as e_rm:
                                st.warning(f"无法删除临时文件 {p_path}: {e_rm}")
                    break
                elif job_data["status"] == "failed":
                    status_text_area.error(f"❌ 任务失败：{job_data.get('error', '未知错误')}")
                    progress_bar.progress(1.0)
                    break
                elif job_data["status"] == "processing":
                    status_text_area.info(f"⏳ 任务处理中... (尝试 {i+1}/{polling_attempts})")
                elif job_data["status"] == "pending":
                    status_text_area.info(f"⏳ 任务待处理... (尝试 {i+1}/{polling_attempts})")
                else:
                    status_text_area.warning(f"⚠️ 任务状态未知: {job_data['status']} (尝试 {i+1}/{polling_attempts})")
                
                time.sleep(int(os.getenv("POLL_INTERVAL_SECONDS", 5))) # 轮询间隔

            except requests.exceptions.RequestException as e:
                status_text_area.error(f"轮询状态失败 (尝试 {i+1}/{polling_attempts}): {e}")
                time.sleep(10) # 网络错误时等待更长时间
            except Exception as e:
                status_text_area.error(f"处理状态时发生错误 (尝试 {i+1}/{polling_attempts}): {e}")
                time.sleep(10)
        else:
            status_text_area.warning("⏰ 分析超时或未能获取最终状态。请检查后端日志或稍后再试。")
            if job_id:
                 st.info(f"你可以稍后使用 Job ID: {job_id} 通过 `/api/job/{job_id}` 端点查询最终状态。")