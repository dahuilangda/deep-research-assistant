# -*- coding: utf-8 -*-
"""
log.py

Copyright (c) 2025 <dahuilangda>
Adapted from:
    ZillizTech Deep Searcher — log utility
    https://github.com/zilliztech/deep-searcher/blob/master/deepsearcher/agent/deep_search.py

License:
    Apache License 2.0
    https://github.com/zilliztech/deep-searcher/blob/master/LICENSE

Description:
    This module provides logging utilities, adapted and modified from the original ZillizTech implementation.
"""

import asyncio
import os
from abc import ABC
from typing import Any, List, Tuple, Dict
import time
import tempfile
import shutil


from openai_llm import BaseLLM
from qanything_utils import QAnythingHandler, split_pdf_and_update_file_to_qanything
from firecrawl_utils import firecrawl_search, firecrawl_scrape

import log

from dotenv import load_dotenv
load_dotenv()


SUB_QUERY_PROMPT = """To answer this question more comprehensively, please break down the original question into up to four sub-questions. Return as list of str.
If this is a very simple question and no decomposition is necessary, then keep the only one original question in the python code list.

Original Question: {original_query}


<EXAMPLE>
Example input:
"Explain deep learning"

Example output:
[
    "What is deep learning?",
    "What is the difference between deep learning and machine learning?",
    "What is the history of deep learning?"
]
</EXAMPLE>

Provide your response in a python code list of str format:
"""

RERANK_PROMPT = """Based on the query questions and the retrieved chunk, to determine whether the chunk is helpful in answering any of the query question, you can only return "YES" or "NO", without any other information.

Query Questions: {query}
Retrieved Chunk: {retrieved_chunk}

Is the chunk helpful in answering the any of the questions?
"""

REFLECT_PROMPT = """Determine whether additional search queries are needed based on the original query, previous sub queries, and all retrieved document chunks. If further research is required, provide a Python list of up to 3 search queries. If no further research is required, return an empty list.

If the original query is to write a report, then you prefer to generate some further queries, instead return an empty list.

Original Query: {question}

Previous Sub Queries: {mini_questions}

Related Chunks:
{mini_chunk_str}

Respond exclusively in valid List of str format without any other text."""


SUMMARY_PROMPT_CN = """你是一位高级调研与分析专家，善于围绕用户提出的各种复杂问题，深入挖掘本质，整合多方材料，撰写结构严谨、逻辑清晰、内容翔实、洞见丰富的专业分析报告、白皮书或提供精确的答案。请综合考虑以下内容：

- 原始问题：准确理解用户的真实意图，澄清分析核心目标、主题与应用场景；明确用户是需要一份详细报告，还是一个直接的答案（如列表、表格、代码等）。
- 子问题拆解：细致梳理并回应全部子问题，形成系统、递进的分析逻辑，确保内容全面且深入（如果适用）。
- 相关文档块：细致研读提供的全部材料，提炼关键数据、事实、理论、案例或观点，并深入分析其专业意义和实际价值。

报告/回答撰写与引用规范：
- **核心原则**：输出的结构和形式应**完全匹配用户问题的复杂度和类型**。
  - **对于复杂问题或明确要求深度分析的场景**：可灵活组织报告结构，例如考虑纳入研究背景、问题阐述、分析方法与数据来源、关键发现及深度洞见、应用案例/场景、局限性、结论与建议、趋势展望等部分。但**仅在这些部分适用且能显著提升回答价值时才使用**。
    - **深入阐述各部分**：若采用此类报告结构，应**通篇考虑**并确保每一个选定的部分都得到**充分且详细的阐述**。内容应翔实具体，通常包含**数个段落**来展开论述，而不仅仅是几句话的概述。
    - **详略得当**：各部分的详略程度应根据其在回应核心问题、支撑整体分析逻辑以及对于最终结论的重要性进行**合理规划与权衡**。关键章节应投入更多笔墨进行深入剖析。力求在每个部分内提供有深度的、全面的信息，而非浅尝辄止。
  - **对于简单问题或要求直接信息的场景**（例如，请求定义、列表、表格、数据提取、代码片段等）：**应提供简洁、直接的回答，避免不必要的报告式结构或冗余章节。** 优先确保信息的准确性和易理解性。
- 总结/结论部分（**如果适用**）：应根据实际分析灵活呈现，可聚焦核心发现、趋势洞察、创新观点或实际建议，避免空洞套路，体现思辨深度和实用价值。若为简单回答，则无需总结。
- 引用要求：
  - 若 `reference` 字段为有效URL，**务必确保**采用 `<sup>[编号](URL)</sup>` 形式嵌入（首次出现时编号，后续重复引用用同一编号），**确保URL被正确渲染为可点击的超链接**。
  - 若 `reference` 字段为本地文件名，采用 `<sup>[编号][文件名]` 形式嵌入。
  - 每个编号仅对应唯一 `reference`，编号顺序按首次引用依次递增。
  - 如无引用文档或引用不适用，则不强行插入引用。
- 不需在文末另列参考文献，所有引用均在文中内嵌。

请基于以下内容撰写专业报告或提供精确回答：

原始查询：{question}
子问题拆解：{mini_questions}
相关文档块：
{mini_chunk_str}
"""

SUMMARY_PROMPT_EN = """You are a senior research and analysis expert skilled at thoroughly exploring and analyzing a wide variety of complex user questions, integrating diverse materials to produce rigorously structured, logically clear, well-supported, and insight-rich professional analysis reports, white papers, or provide precise answers. Please proceed as follows:

- Original Question: Accurately understand the user's intent and clarify the core objective, theme, and context for analysis. Determine if the user requires a detailed report or a direct answer (e.g., a list, table, code, etc.).
- Sub-question Decomposition: Carefully address all sub-questions, building a systematic and progressive logic for a comprehensive and in-depth analysis (if applicable).
- Relevant Document Chunks: Diligently review all provided materials, extract key data, facts, theories, cases, or perspectives, and deeply analyze their professional significance and practical value.

Report/Answer Writing & Citation Guidelines:
- **Core Principle**: The structure and format of your output should **directly match the complexity and type of the user's question**.
  - **For complex questions or when in-depth analysis is explicitly requested**: You may flexibly organize a report structure. For instance, consider including sections such as Research Background, Problem Statement, Methodology & Data Sources, Key Findings & In-depth Insights, Application Scenarios/Case Studies, Limitations, Conclusions & Recommendations, and Trend Outlook. However, **use these sections only if they are appropriate and significantly enhance the value of the response**.
    - **Substantial Development of Sections**: If such a report structure is adopted, ensure a **holistic consideration** where each selected section is **thoroughly and substantially developed**. Content should be specific and detailed, typically comprising **multiple paragraphs** to elaborate on points, not just a few overview sentences.
    - **Proportional Detail**: The depth and length of each section should be **proportionally planned and balanced** according to its importance in addressing the core query, supporting the overall analytical narrative, and contributing to the final conclusions. Key sections should receive more detailed analysis. Strive for comprehensive and insightful coverage within each section, avoiding superficial treatment.
  - **For simple questions or requests for direct information** (e.g., definitions, lists, tables, data extraction, code snippets): **Provide a concise, direct answer. Avoid unnecessary report-like structures or superfluous sections.** Prioritize accuracy and clarity of information.
- Summary/Conclusion section (**if applicable**): Should be adaptive according to your analysis—highlight key findings, trends, original insights, or practical recommendations, avoiding boilerplate conclusions and demonstrating depth and real-world value. If providing a simple answer, a summary is likely not needed.
- Citation requirements:
  - If the `reference` field is a valid URL, **ensure you embed it inline correctly as** `<sup>[n](URL)</sup>` (numbered on first appearance, reused for repeated citations), **making sure the URL is properly rendered as a clickable hyperlink**.
  - If the `reference` is a local filename, use `<sup>[n][filename]</sup>`.
  - Each number uniquely matches one `reference`, numbered sequentially as first used.
  - If no suitable citations are present or citations are not applicable, do not force their insertion.
- Do **not** include a separate reference list at the end; all citations are inline only.

Please write your professional report or provide a precise answer based on the following:

Original Question: {question}
Sub-question Decomposition: {mini_questions}
Relevant Document Chunks:
{mini_chunk_str}
"""

LANG = os.getenv("OUTPUT_LANG", "zh").lower()
SUMMARY_PROMPT = SUMMARY_PROMPT_EN if LANG.startswith("en") else SUMMARY_PROMPT_CN

class RetrievalResult:
    """
    Represents a result retrieved from QAnything or Firecrawl.
    """
    def __init__(
        self,
        text: str,
        reference: str,
        metadata: dict,
        score: float = 0.0,
    ):
        self.text = text
        self.reference = reference # Can be URL, filename, or None
        self.metadata = metadata
        self.score: float = score

    def __repr__(self):
        return f"RetrievalResult(score={self.score}, text='{self.text[:50]}...', reference='{self.reference}', metadata={self.metadata})"

def deduplicate_results(results: List[RetrievalResult]) -> List[RetrievalResult]:
    all_text_set = set()
    deduplicated_results = []
    for result in results:
        identifier = (result.text, result.reference) # Using text and reference for uniqueness
        if identifier not in all_text_set:
            all_text_set.add(identifier)
            deduplicated_results.append(result)
    return deduplicated_results

# MODIFICATION: Add a sort and limit utility for results
def sort_and_limit_results(results: List[RetrievalResult], max_count: int) -> List[RetrievalResult]:
    """Sorts results by score (descending) and limits the count."""
    if not results:
        return []
    # Sort by score in descending order. Results with higher scores come first.
    sorted_results = sorted(results, key=lambda r: r.score, reverse=True)
    return sorted_results[:max_count]


def describe_class(description):
    def decorator(cls):
        cls.__description__ = description
        return cls
    return decorator

class BaseAgent(ABC):
    def __init__(self, **kwargs):
        pass

    def invoke(self, query: str, **kwargs) -> Any:
        pass

class RAGAgent(BaseAgent):
    def __init__(self, **kwargs):
        pass

    def retrieve(self, query: str, **kwargs) -> Tuple[List[RetrievalResult], int, dict]:
        pass

    def query(self, query: str, **kwargs) -> Tuple[str, List[RetrievalResult], int]:
        pass

@describe_class(
    "This agent is suitable for handling general and simple queries, leveraging QAnything for KB search (including uploaded files and URLs) and Firecrawl for web search, then writing a report."
)
class DeepSearch(RAGAgent):
    def __init__(
        self,
        llm: BaseLLM,
        qanything_handler: QAnythingHandler,
        qanything_kb_ids: List[str],
        firecrawl_api_url: str,
        max_iter: int = 3,
        search_internet: bool = False,
        max_qanything_chunks_to_rerank: int = 5, 
        max_firecrawl_qanything_chunks_to_process: int = 10, 
        min_qanything_results_before_web_search: int = 2, 
        max_chunks_for_summary: int = 25, 
        **kwargs,
    ):
        self.llm = llm
        self.qanything_handler = qanything_handler
        self.qanything_kb_ids = qanything_kb_ids
        self.max_iter = max_iter
        self.search_internet = search_internet
        self.firecrawl_api_url = firecrawl_api_url

        # Store new parameters
        self.max_qanything_chunks_to_rerank = max_qanything_chunks_to_rerank
        self.max_firecrawl_qanything_chunks_to_process = max_firecrawl_qanything_chunks_to_process
        self.min_qanything_results_before_web_search = min_qanything_results_before_web_search
        self.max_chunks_for_summary = max_chunks_for_summary

        if firecrawl_scrape is None:
             log.color_print("<warning> 'firecrawl_scrape' function was not imported. Direct URL processing via 'urls' parameter will be skipped if attempted. 'firecrawl_search' for web queries is available.</warning>\n")


    def _generate_sub_queries(self, original_query: str) -> Tuple[List[str], int]:
        chat_response = self.llm.chat(
            messages=[
                {"role": "user", "content": SUB_QUERY_PROMPT.format(original_query=original_query)}
            ]
        )
        response_content = self.llm.remove_think(chat_response.content)
        try:
            return self.llm.literal_eval(response_content), chat_response.total_tokens
        except ValueError as e:
            log.color_print(f"<error>Error parsing sub_queries: {e} Content: {response_content}</error>\n")
            return [original_query], chat_response.total_tokens


    async def _search_and_rerank_qanything(self, query: str, sub_queries_context: List[str]) -> Tuple[List[RetrievalResult], int]:
        retrieved_for_query = []
        total_tokens_consumed = 0

        if not self.qanything_kb_ids:
            log.color_print(f"<search_qanything_warn> No QAnything KB IDs provided for query: {query}. Skipping QAnything search.</search_qanything_warn>\n")
            return [], 0

        log.color_print(f"<search_qanything> Searching QAnything for: [{query}] in KBs: {self.qanything_kb_ids}...</search_qanything>\n")

        qa_response = self.qanything_handler.chat(
            question=query,
            kb_ids=self.qanything_kb_ids,
            only_need_search_results=True,
        )

        if qa_response.get("code") == 200 and "source_documents" in qa_response:
            source_documents = qa_response["source_documents"]
            log.color_print(f"<search_qanything> Found {len(source_documents)} potential chunks from QAnything for query '{query}'.</search_qanything>\n")

            docs_to_rerank = sorted(source_documents, key=lambda d: float(d.get('score', 0.0)), reverse=True)
            docs_to_rerank = docs_to_rerank[:self.max_qanything_chunks_to_rerank]
            log.color_print(f"<search_qanything> Reranking top {len(docs_to_rerank)} chunks (max_qanything_chunks_to_rerank={self.max_qanything_chunks_to_rerank})...</search_qanything>\n")

            accepted_chunk_count = 0
            for doc in docs_to_rerank: # Iterate over the limited and sorted list
                rerank_messages = [
                    {
                        "role": "user",
                        "content": RERANK_PROMPT.format(
                            query=[query] + sub_queries_context,
                            retrieved_chunk=f"<chunk>{doc.get('content', '')}</chunk>",
                        ),
                    }
                ]
                chat_response_rerank = self.llm.chat(rerank_messages)
                total_tokens_consumed += chat_response_rerank.total_tokens
                rerank_decision = self.llm.remove_think(chat_response_rerank.content).strip().upper()

                if "YES" in rerank_decision and "NO" not in rerank_decision:
                    retrieved_for_query.append(
                        RetrievalResult(
                            text=doc.get('content', ''),
                            reference=doc.get('file_name', 'N/A'),
                            score=float(doc.get('score', 0.0)),
                            metadata={
                                'file_id': doc.get('file_id'),
                                'kb_id_searched': doc.get('kb_id', self.qanything_kb_ids[0] if self.qanything_kb_ids else 'N/A'),
                                'retrieval_query': doc.get('retrieval_query'),
                                'embed_version': doc.get('embed_version'),
                                'source': 'qanything'
                            }
                        )
                    )
                    accepted_chunk_count +=1
            if accepted_chunk_count > 0:
                log.color_print(f"<search_qanything> Accepted {accepted_chunk_count} chunk(s) from QAnything for query '{query}' after reranking.</search_qanything>\n")
            else:
                log.color_print(f"<search_qanything> No chunks accepted from QAnything for query '{query}' after reranking.</search_qanything>\n")
        else:
            log.color_print(f"<search_qanything> No source documents found or error in QAnything response for query '{query}'. Response: {qa_response}</search_qanything>\n")

        return retrieved_for_query, total_tokens_consumed

    async def _search_and_rerank_firecrawl(
        self,
        query: str,
        sub_queries_context: List[str],
        processed_urls_in_session: set,
        upload_mode: str = "strong",
        chunk_size: int = 800,
        **kwargs
    ) -> Tuple[List[RetrievalResult], int]:
        retrieved_for_query: List[RetrievalResult] = []
        total_tokens_consumed = 0

        if not self.qanything_kb_ids:
            log.color_print(f"<search_firecrawl_warn> No QAnything KB IDs configured. Cannot upload Firecrawl results. Skipping web search for '{query}'.</search_firecrawl_warn>\n")
            return [], 0
        target_kb_id = self.qanything_kb_ids[0]

        log.color_print(f"<search_firecrawl> Web searching via Firecrawl for: [{query}] and uploading to KB {target_kb_id}...</search_firecrawl>\n")
        try:
            scrape_opts = {"formats": ["markdown"]}
            if 'max_web_search_results' in kwargs:
                max_web_search_results = kwargs['max_web_search_results']
            else:
                max_web_search_results = 5
            fc_response = firecrawl_search(query=query, limit=max_web_search_results, scrape_options=scrape_opts) # Limit search results to reduce processing
        except Exception as e:
            log.color_print(f"<search_firecrawl_error> Firecrawl search error: {e}</search_firecrawl_error>\n")
            return [], 0

        pages = fc_response.get("data", []) or []
        if not pages:
            log.color_print(f"<search_firecrawl> Firecrawl returned no results for query: '{query}'</search_firecrawl>\n")
            return [], 0

        temp_dir = tempfile.mkdtemp(prefix="firecrawl_search_")
        newly_uploaded_urls_this_call = set()

        for page in pages:
            url = page.get("url", "")
            if not url:
                log.color_print(f"<search_firecrawl_warn> Firecrawl result for query '{query}' missing URL. Skipping.</search_firecrawl_warn>\n")
                continue

            if url in processed_urls_in_session:
                log.color_print(f"<search_firecrawl_skip_upload> Content for URL '{url}' (from web search for '{query}') was already processed and uploaded in this session. Skipping re-upload.</search_firecrawl_skip_upload>\n")
                continue

            content = page.get("markdown") or page.get("content")
            if not content:
                log.color_print(f"<search_firecrawl_warn> No content/markdown for URL {url} from query '{query}'. Skipping.</search_firecrawl_warn>\n")
                continue

            safe_name = "".join(c if c.isalnum() else "_" for c in url.replace("https://", "").replace("http://", ""))[:100]
            md_path = os.path.join(temp_dir, f"{safe_name}.md")

            with open(md_path, "w", encoding="utf-8") as f:
                f.write(f"# Content from web search: {query}\n## Source URL: {url}\n\n{content}")

            try:
                upload_resp = self.qanything_handler.upload_file(
                    file=md_path,
                    kb_id=target_kb_id,
                    mode=upload_mode,
                    chunk_size=chunk_size
                )
                file_id = upload_resp["data"][0]["file_id"]
                status = self.qanything_handler.wait_status_to_end(target_kb_id, file_id)
                if status != "green":
                    log.color_print(f"<search_firecrawl_error> QAnything indexing failed for Firecrawl result: {md_path} (URL: {url})</search_firecrawl_error>\n")
                    continue
                else:
                    log.color_print(f"<search_firecrawl> QAnything indexed Firecrawl result successfully: {md_path} (URL: {url})</search_firecrawl>\n")
                    processed_urls_in_session.add(url)
                    newly_uploaded_urls_this_call.add(url)
            except Exception as e:
                log.color_print(f"<search_firecrawl_error> QAnything upload error for Firecrawl result (URL: {url}): {e}</search_firecrawl_error>\n")
                continue

        if newly_uploaded_urls_this_call or any(page.get("url") in processed_urls_in_session for page_data in pages if page_data.get("url")):
            try:
                prompt_ctx = ""
                if sub_queries_context:
                    prompt_ctx = ("以下是针对该查询拆分出的子问题，\n"
                                  "请结合它们来优化检索：\n- " + "\n- ".join(sub_queries_context))
                qa_resp = self.qanything_handler.chat(
                    question=query,
                    kb_ids=[target_kb_id],
                    only_need_search_results=True,
                    custom_prompt=prompt_ctx,
                    networking=False,
                    rerank=True # Using QAnything's internal rerank for these results
                )
                if qa_resp.get("code") == 200 and "source_documents" in qa_resp:
                    # MODIFICATION: Sort by score and limit before adding to results
                    source_docs_firecrawl = qa_resp["source_documents"]
                    docs_to_process = sorted(source_docs_firecrawl, key=lambda d: float(d.get('score', 0.0)), reverse=True)
                    docs_to_process = docs_to_process[:self.max_firecrawl_qanything_chunks_to_process]
                    log.color_print(f"<search_firecrawl> Processing top {len(docs_to_process)} chunks from QAnything for Firecrawl content (max_firecrawl_qanything_chunks_to_process={self.max_firecrawl_qanything_chunks_to_process}).</search_firecrawl>\n")

                    accepted_chunks_summary: Dict[Tuple[Any, str], int] = {}

                    for doc in docs_to_process: # Iterate over limited and sorted list
                        doc_metadata = {
                                    "file_id": doc.get("file_id"),
                                    "source": "firecrawl_web_search_via_qanything",
                                    "orig_query": query,
                                    "retrieved_doc_filename": doc.get("file_name", "")
                                }
                        current_doc_filename: Any = doc.get('file_name')
                        retrieved_url_ref: Any = current_doc_filename

                        if current_doc_filename:
                            for page_item in pages:
                                page_item_url = page_item.get("url", "")
                                if page_item_url:
                                    s_name_from_page_item = "".join(c if c.isalnum() else "_" for c in page_item_url.replace("https://", "").replace("http://", ""))[:100] + ".md"
                                    if current_doc_filename == s_name_from_page_item:
                                        retrieved_url_ref = page_item_url
                                        break
                        retrieved_for_query.append(
                            RetrievalResult(
                                text=doc.get("content", ""),
                                reference=retrieved_url_ref,
                                score=float(doc.get("score", 0.0)),
                                metadata=doc_metadata
                            )
                        )
                        summary_key = (retrieved_url_ref, query)
                        accepted_chunks_summary[summary_key] = accepted_chunks_summary.get(summary_key, 0) + 1
                    for (url_ref_from_key, q_text_from_key), count in accepted_chunks_summary.items():
                        log.color_print(f"<search_firecrawl> Accepted {count} chunk(s) from QAnything for Firecrawl-sourced content (Ref: {url_ref_from_key}) for query '{q_text_from_key}'</search_firecrawl>\n")
                else:
                    log.color_print(f"<search_firecrawl> No source documents found in QAnything or error for query '{query}' after Firecrawl uploads. Response: {qa_resp}</search_firecrawl>\n")
            except Exception as e:
                log.color_print(f"<search_firecrawl_error> QAnything retrieval error for query '{query}' after Firecrawl uploads: {e}</search_firecrawl_error>\n")

        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        except Exception as e:
            log.color_print(f"<search_firecrawl_cleanup_error> Error removing temp Firecrawl dir {temp_dir}: {e}</search_firecrawl_cleanup_error>\n")

        return retrieved_for_query, total_tokens_consumed # total_tokens_consumed for LLM reranking not applicable here

    def _generate_gap_queries(
        self, original_query: str, all_sub_queries: List[str], all_chunks: List[RetrievalResult]
    ) -> Tuple[List[str], int]:
        if len(all_chunks) > 0:
            texts = [chunk.text for chunk in all_chunks]
            refs = [chunk.reference for chunk in all_chunks]
            mini_chunk_str = self._format_chunk_texts_for_reflection(texts, refs)
        else:
            mini_chunk_str = "NO RELATED CHUNKS FOUND."

        reflect_prompt_content = REFLECT_PROMPT.format(
            question=original_query,
            mini_questions=all_sub_queries,
            mini_chunk_str=mini_chunk_str,
        )
        chat_response = self.llm.chat([{"role": "user", "content": reflect_prompt_content}])
        response_content = self.llm.remove_think(chat_response.content)
        try:
            return self.llm.literal_eval(response_content), chat_response.total_tokens
        except ValueError as e:
            log.color_print(f"<error>Error parsing gap_queries: {e}. Content: {response_content}</error>\n")
            return [], chat_response.total_tokens


    async def _upload_files_to_qanything(
        self,
        file_paths: List[str],
        kb_id: str,
        num_split_pdf: int = 0,
        chunk_size_qa: int = 800
    ):
        output_split_path_base = "./temp_qanything_uploads"
        os.makedirs(output_split_path_base, exist_ok=True)
        temp_split_dir = tempfile.mkdtemp(dir=output_split_path_base)

        for file_path in file_paths:
            if not os.path.exists(file_path):
                log.color_print(f"<qanything_upload_error> File not found: {file_path}. Skipping.</qanything_upload_error>\n")
                continue

            log.color_print(f"<qanything_upload> Processing file for QAnything: {file_path} into KB: {kb_id}</qanything_upload>\n")
            try:
                if file_path.lower().endswith(".pdf") and num_split_pdf > 0:
                    log.color_print(f"<qanything_upload> Splitting PDF {file_path} into {num_split_pdf}-page chunks and uploading.</qanything_upload>\n")
                    split_pdf_and_update_file_to_qanything(
                        pdf_file=file_path,
                        output_path=temp_split_dir,
                        qanything_handler=self.qanything_handler,
                        kb_id=kb_id,
                        num_split=num_split_pdf
                    )
                    log.color_print(f"<qanything_upload> Finished splitting and uploading PDF: {file_path}</qanything_upload>\n")
                else:
                    log.color_print(f"<qanything_upload> Directly uploading file: {file_path} (QAnything chunk_size: {chunk_size_qa})</qanything_upload>\n")
                    upload_resp = self.qanything_handler.upload_file(
                        file=file_path,
                        kb_id=kb_id,
                        mode="strong",
                        chunk_size=chunk_size_qa
                    )
                    if upload_resp.get("code") == 200 and upload_resp.get("data"):
                        file_id = upload_resp["data"][0]["file_id"]
                        status = self.qanything_handler.wait_status_to_end(kb_id, file_id)
                        if status == "green":
                            log.color_print(f"<qanything_upload> QAnything indexed successfully: {file_path}</qanything_upload>\n")
                        else:
                            log.color_print(f"<qanything_upload_error> QAnything indexing FAILED for: {file_path} (status: {status})</qanything_upload_error>\n")
                    else:
                        log.color_print(f"<qanything_upload_error> QAnything upload FAILED for: {file_path}. Response: {upload_resp}</qanything_upload_error>\n")
            except Exception as e:
                log.color_print(f"<qanything_upload_exception> Error processing file {file_path}: {e}</qanything_upload_exception>\n")
        try:
            if os.path.exists(temp_split_dir):
                 shutil.rmtree(temp_split_dir)
        except Exception as e:
            log.color_print(f"<qanything_upload_cleanup_error> Error removing temp upload directory {temp_split_dir}: {e}</qanything_upload_cleanup_error>\n")


    def retrieve(self, original_query: str, **kwargs) -> Tuple[List[RetrievalResult], int, dict]:
        files = kwargs.pop("files", None)
        urls = kwargs.pop("urls", None)
        search_web = kwargs.pop("search_web", None)
        qanything_upload_num_split_pdf = kwargs.pop("qanything_upload_num_split_pdf", 0)
        qanything_upload_chunk_size = kwargs.pop("qanything_upload_chunk_size", 800)

        return asyncio.run(self.async_retrieve(
            original_query,
            files=files,
            urls=urls,
            search_web=search_web,
            qanything_upload_num_split_pdf=qanything_upload_num_split_pdf,
            qanything_upload_chunk_size=qanything_upload_chunk_size,
            **kwargs
        ))

    async def async_retrieve(
        self,
        original_query: str,
        files: List[str] = None,
        urls: List[str] = None,
        search_web: bool = None, # If None, use self.search_internet
        qanything_upload_num_split_pdf: int = 0,
        qanything_upload_chunk_size: int = 800,
        **kwargs
    ) -> Tuple[List[RetrievalResult], int, dict]:
        max_iter_actual = kwargs.pop("max_iter", self.max_iter)
        search_internet_actual = search_web if search_web is not None else self.search_internet

        log.color_print(f"<query> Original Query: {original_query} </query>\n")
        log.color_print(f"<params> Files: {files}, URLs: {urls}, Search Web Active: {search_internet_actual}, PDF Split Pages: {qanything_upload_num_split_pdf}, QA Chunk Size: {qanything_upload_chunk_size} </params>\n")
        log.color_print(f"<params_limits> Max QA rerank: {self.max_qanything_chunks_to_rerank}, Max FC QA process: {self.max_firecrawl_qanything_chunks_to_process}, Min QA for web: {self.min_qanything_results_before_web_search}, Max for summary: {self.max_chunks_for_summary} </params_limits>\n")

        all_search_res: List[RetrievalResult] = []
        all_sub_queries: List[str] = []
        total_tokens: int = 0

        processed_urls_in_session = set()

        if not self.qanything_kb_ids:
            log.color_print("<error> No QAnything KB IDs configured for DeepSearch.</error>\n")
            if files or urls:
                 raise ValueError("QAnything KB ID is required for file or URL processing, but none are configured.")
            target_kb_id = None
        else:
            target_kb_id = self.qanything_kb_ids[0]

        if target_kb_id:
            if files:
                log.color_print(f"<preprocess_files> Uploading {len(files)} local files to QAnything KB: {target_kb_id}...</preprocess_files>\n")
                await self._upload_files_to_qanything(
                    file_paths=files,
                    kb_id=target_kb_id,
                    num_split_pdf=qanything_upload_num_split_pdf,
                    chunk_size_qa=qanything_upload_chunk_size
                )
                log.color_print(f"<preprocess_files> Finished uploading local files.</preprocess_files>\n")

            if urls:
                if not firecrawl_scrape:
                    log.color_print("<error> 'firecrawl_scrape' is not available (import failed). Skipping processing of direct URLs.</error>\n")
                else:
                    unique_input_urls = list(set(urls or []))
                    if not unique_input_urls:
                        log.color_print(f"<preprocess_urls> No unique URLs provided. Skipping direct URL processing.</preprocess_urls>\n")
                    else:
                        log.color_print(f"<preprocess_urls> Scraping and uploading content from {len(unique_input_urls)} unique URLs to QAnything KB: {target_kb_id}...</preprocess_urls>\n")
                        temp_url_md_dir = tempfile.mkdtemp(prefix="direct_urls_md_")
                        for url_to_scrape in unique_input_urls:
                            if url_to_scrape in processed_urls_in_session:
                                log.color_print(f"<preprocess_url_skip> Content for URL '{url_to_scrape}' already processed in this session. Skipping.</preprocess_url_skip>\n")
                                continue
                            try:
                                log.color_print(f"<preprocess_url_scrape> Scraping URL: {url_to_scrape} using API {self.firecrawl_api_url}...</preprocess_url_scrape>\n")
                                scrape_opts = {"formats": ["markdown"]}
                                fc_page_data = await asyncio.to_thread(
                                    firecrawl_scrape,
                                    url_to_scrape=url_to_scrape,
                                    scrape_options=scrape_opts,
                                )
                                fc_page_data = fc_page_data.get("data", {})

                                if fc_page_data and (fc_page_data.get("markdown") or fc_page_data.get("content")):
                                    content = fc_page_data.get("markdown") or fc_page_data.get("content")
                                    if not content:
                                        log.color_print(f"<preprocess_url_warn> No content extracted from URL: {url_to_scrape}. Skipping.</preprocess_url_warn>\n")
                                        continue

                                    safe_name = "".join(c if c.isalnum() else "_" for c in url_to_scrape.replace("https://", "").replace("http://", ""))[:100]
                                    md_path = os.path.join(temp_url_md_dir, f"{safe_name}.md")

                                    with open(md_path, "w", encoding="utf-8") as f:
                                        f.write(f"# Content from URL: {url_to_scrape}\n\n{content}")

                                    log.color_print(f"<preprocess_url_upload> Uploading scraped content from {url_to_scrape} (as {md_path}) to QAnything...</preprocess_url_upload>\n")
                                    upload_resp = self.qanything_handler.upload_file(
                                        file=md_path,
                                        kb_id=target_kb_id,
                                        mode="strong",
                                        chunk_size=qanything_upload_chunk_size,
                                    )
                                    if upload_resp.get("code") == 200 and upload_resp.get("data"):
                                        file_id = upload_resp["data"][0]["file_id"]
                                        status = self.qanything_handler.wait_status_to_end(target_kb_id, file_id)
                                        if status == "green":
                                            log.color_print(f"<preprocess_url_success> QAnything indexed successfully: {url_to_scrape}</preprocess_url_success>\n")
                                            processed_urls_in_session.add(url_to_scrape)
                                        else:
                                            log.color_print(f"<preprocess_url_error> QAnything indexing FAILED for: {url_to_scrape} (status: {status})</preprocess_url_error>\n")
                                    else:
                                        log.color_print(f"<preprocess_url_error> QAnything upload FAILED for scraped content of {url_to_scrape}. Response: {upload_resp}</preprocess_url_error>\n")
                                else:
                                    log.color_print(f"<preprocess_url_error> Could not scrape meaningful content for URL: {url_to_scrape}. Response: {fc_page_data}</preprocess_url_error>\n")
                            except Exception as e:
                                log.color_print(f"<preprocess_url_exception> Error processing URL {url_to_scrape}: {e}</preprocess_url_exception>\n")
                        try:
                            if os.path.exists(temp_url_md_dir):
                                shutil.rmtree(temp_url_md_dir)
                        except Exception as e:
                            log.color_print(f"<preprocess_url_cleanup_error> Error removing temp URL MD directory {temp_url_md_dir}: {e}</preprocess_url_cleanup_error>\n")
                        log.color_print(f"<preprocess_urls> Finished processing specified URLs.</preprocess_urls>\n")

        sub_queries, used_token = self._generate_sub_queries(original_query)
        total_tokens += used_token
        if not sub_queries:
            log.color_print("<think> No sub queries were generated. Using original query.</think>\n")
            sub_queries = [original_query]
        else:
            log.color_print(f"<think> Initial sub queries: {sub_queries}</think>\n")
        all_sub_queries.extend(sub_queries)
        sub_gap_queries = sub_queries # Queries to be processed in the current/next iteration

        for iter_count in range(max_iter_actual):
            log.color_print(f">> Iteration: {iter_count + 1}\n")

            if not sub_gap_queries:
                log.color_print("<think> No gap queries to process. Exiting loop.</think>\n")
                break

            current_iteration_chunks: List[RetrievalResult] = []
            qanything_results_for_current_iter: Dict[str, List[RetrievalResult]] = {}


            # --- QAnything Search Phase for current sub_gap_queries ---
            if target_kb_id: # Only search QAnything if a KB is configured
                qanything_search_tasks = []
                for s_query in sub_gap_queries:
                    qanything_search_tasks.append(self._search_and_rerank_qanything(s_query, all_sub_queries))

                if qanything_search_tasks:
                    gathered_qanything_results = await asyncio.gather(*qanything_search_tasks)
                    temp_idx = 0
                    for s_query in sub_gap_queries: # Assuming results align with sub_gap_queries
                        partial_results, tokens_consumed_partial = gathered_qanything_results[temp_idx]
                        qanything_results_for_current_iter[s_query] = partial_results
                        current_iteration_chunks.extend(partial_results)
                        total_tokens += tokens_consumed_partial
                        temp_idx += 1
            else:
                 for s_query in sub_gap_queries:
                    qanything_results_for_current_iter[s_query] = []

            # --- Firecrawl Web Search Phase (Conditional) ---
            firecrawl_search_tasks = []
            if search_internet_actual:
                for s_query in sub_gap_queries:
                    qanything_found_enough = len(qanything_results_for_current_iter.get(s_query, [])) >= self.min_qanything_results_before_web_search

                    if not qanything_found_enough:
                        log.color_print(f"<think_web_search> QAnything results for '{s_query}' ({len(qanything_results_for_current_iter.get(s_query, []))}) are less than threshold ({self.min_qanything_results_before_web_search}). Proceeding with web search.</think_web_search>\n")
                        firecrawl_search_tasks.append(self._search_and_rerank_firecrawl(
                            s_query,
                            all_sub_queries,
                            processed_urls_in_session,
                            chunk_size=qanything_upload_chunk_size,
                            **kwargs
                        ))
                    else:
                        log.color_print(f"<think_skip_web_search> QAnything found sufficient results ({len(qanything_results_for_current_iter.get(s_query, []))}) for '{s_query}'. Skipping web search for this sub-query.</think_skip_web_search>\n")

            if firecrawl_search_tasks:
                gathered_firecrawl_results = await asyncio.gather(*firecrawl_search_tasks)
                for partial_results, tokens_consumed_partial in gathered_firecrawl_results:
                    current_iteration_chunks.extend(partial_results)
                    total_tokens += tokens_consumed_partial # Note: _search_and_rerank_firecrawl currently returns 0 for LLM tokens

            current_iteration_chunks = deduplicate_results(current_iteration_chunks)
            all_search_res.extend(current_iteration_chunks)
            all_search_res = deduplicate_results(all_search_res) # Deduplicate across iterations too

            if iter_count == max_iter_actual - 1:
                log.color_print("<think> Reached maximum iterations. Exiting search loop.</think>\n")
                break

            log.color_print("<think> Reflecting on search results...</think>\n")
            reflection_chunks = sort_and_limit_results(all_search_res, self.max_chunks_for_summary + 10)

            new_gap_queries, consumed_token_reflect = self._generate_gap_queries(
                original_query, list(set(all_sub_queries)), reflection_chunks
            )
            total_tokens += consumed_token_reflect

            if not new_gap_queries:
                log.color_print("<think> No new gap queries from reflection. Exiting search loop.</think>\n")
                break
            else:
                truly_new_queries = [q for q in new_gap_queries if q not in all_sub_queries]
                if not truly_new_queries:
                    log.color_print("<think> Reflection generated only already processed queries. Exiting.</think>\n")
                    break
                sub_gap_queries = truly_new_queries
                log.color_print(f"<think> New gap queries for next iteration: {sub_gap_queries}</think>\n")
                all_sub_queries.extend(sub_gap_queries)

        all_search_res = deduplicate_results(all_search_res)
        all_search_res = sort_and_limit_results(all_search_res, self.max_chunks_for_summary)
        log.color_print(f"<retrieve_summary> Total unique retrieved chunks after final limit: {len(all_search_res)} (max_chunks_for_summary={self.max_chunks_for_summary})</retrieve_summary>\n")

        additional_info = {"all_sub_queries": list(set(all_sub_queries))}
        return all_search_res, total_tokens, additional_info

    def query(self, query: str, **kwargs) -> Tuple[str, List[RetrievalResult], int]:
        files = kwargs.pop("files", None)
        urls = kwargs.pop("urls", None)
        search_web = kwargs.pop("search_web", None)
        qanything_upload_num_split_pdf = kwargs.pop("qanything_upload_num_split_pdf", 0)
        qanything_upload_chunk_size = kwargs.pop("qanything_upload_chunk_size", 800)


        all_retrieved_results, n_token_retrieval, additional_info = self.retrieve(
            query,
            files=files,
            urls=urls,
            search_web=search_web,
            qanything_upload_num_split_pdf=qanything_upload_num_split_pdf,
            qanything_upload_chunk_size=qanything_upload_chunk_size,
            **kwargs
        )

        if not all_retrieved_results:
            log.color_print(f"<query_summary>No relevant information found for query '{query}'.</query_summary>\n")
            return f"对不起，关于查询 '{query}' 未能找到足够的相关信息来生成报告。", [], n_token_retrieval

        all_sub_queries = additional_info.get("all_sub_queries", [query])
        formatted_chunks_for_summary, _ = self._format_chunk_texts_for_summary(all_retrieved_results)

        log.color_print(
            f"<think> Summarizing answer from {len(all_retrieved_results)} retrieved chunks for query '{query}' (max_chunks_for_summary={self.max_chunks_for_summary})...</think>\n"
        )
        summary_prompt_content = SUMMARY_PROMPT.format(
            question=query,
            mini_questions=all_sub_queries,
            mini_chunk_str=formatted_chunks_for_summary,
        )

        chat_response = self.llm.chat([{"role": "user", "content": summary_prompt_content}])

        final_answer = self.llm.remove_think(chat_response.content)
        log.color_print("\n==== FINAL ANSWER ====\n")
        log.color_print(final_answer)

        return (
            final_answer,
            all_retrieved_results,
            n_token_retrieval + chat_response.total_tokens,
        )

    def _format_chunk_texts_for_reflection(self, chunk_texts: List[str], references: List[str]) -> str:
        chunk_str = ""
        for i, (chunk, ref) in enumerate(zip(chunk_texts, references)):
            chunk_str += f"""<chunk_{i} reference="{ref}">\n{chunk[:500]}...\n</chunk_{i}>\n"""
        return chunk_str

    def _format_chunk_texts_for_summary(self, retrieved_results: List[RetrievalResult]) -> Tuple[str, Dict[str, int]]:
        chunk_str = ""
        for i, result in enumerate(retrieved_results):
            chunk_str += f"""<chunk_{i} reference="{result.reference}">\n{result.text}\n</chunk_{i}>\n\n"""

        return chunk_str.strip(), {}


if __name__ == "__main__":
    from openai_llm import OpenAI

    # --- Configuration ---
    # 1) 从环境读取
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
    OPENAI_MODEL_NAME = os.getenv("OPENAI_MODEL_NAME")
    QANYTHING_SERVER_URL = os.getenv("QANYTHING_SERVER_URL")
    QANYTHING_USER_ID = os.getenv("QANYTHING_USER_ID")
    FIRECRAWL_API_URL = os.getenv("FIRECRAWL_API_URL")

    # Ensure environment variables are set for OpenAI for the llm instance
    os.environ["OPENAI_API_KEY"] = OPENAI_API_KEY
    os.environ["OPENAI_BASE_URL"] = OPENAI_BASE_URL

    # ---- Instantiate LLM ----
    llm_instance = OpenAI(model=OPENAI_MODEL_NAME)


    # --- QAnything Setup ---
    qanything_handler = QAnythingHandler(
        server_url=QANYTHING_SERVER_URL,
        user_id=QANYTHING_USER_ID)
    kb_id_to_use = None
    kb_name = f"deep_search_mod_kb_{int(time.time())}"
    try:
        response = qanything_handler.create_knowledge_base(kb_name)
        if response.get("code") == 200 and response.get("data", {}).get("kb_id"):
            kb_id_to_use = response.get("data", {}).get("kb_id")
            log.color_print(f"<setup>Created QAnything KB: {kb_name} with ID: {kb_id_to_use}</setup>\n")
        else:
            log.color_print(f"<setup_error>Failed to create QAnything KB. Response: {response}</setup_error>\n")
            # Try to find an existing KB if creation fails (e.g., if name conflict or other issue)
            kbs = qanything_handler.list_knowledge_bases()
            if kbs.get("data"):
                # Fallback to the first available KB if creation failed
                kb_id_to_use = kbs["data"][0].get("kb_id")
                kb_name = kbs["data"][0].get("kb_name")
                log.color_print(f"<setup_warn>Using existing KB: {kb_name} (ID: {kb_id_to_use}) as fallback.</setup_warn>\n")
            else:
                 log.color_print(f"<setup_error>No existing KBs found either. Some tests might fail.</setup_error>\n")

    except Exception as e:
        log.color_print(f"<setup_exception>QAnything setup failed: {e}. Some tests might fail or be skipped.</setup_exception>\n")


    # --- Sample Data ---
    sample_pdf_path = os.path.join(os.path.dirname(__file__), "..", "data", "WhatisMilvus.pdf") # Adjust path as needed
    if not os.path.exists(sample_pdf_path):
        log.color_print(f"<warning_main>Sample PDF not found at {sample_pdf_path}. Creating a dummy one.</warning_main>\n")
        os.makedirs(os.path.dirname(sample_pdf_path), exist_ok=True)
        with open(sample_pdf_path, "w") as f:
            f.write("This is a dummy PDF content about Milvus for testing.")

    def _bool(env_var, default=False):
        return os.getenv(env_var, str(default)).lower() in ("1","true","yes")
    def _int(env_var, default):
        try: return int(os.getenv(env_var, default))
        except: return default

    deep_search_agent = DeepSearch(
        llm=llm_instance,
        qanything_handler=qanything_handler,
        qanything_kb_ids=[kb_id_to_use] if kb_id_to_use else [],
        max_iter       = _int("MAX_ITER", 3),
        search_internet= _bool("SEARCH_INTERNET", False),
        firecrawl_api_url= FIRECRAWL_API_URL,
        max_qanything_chunks_to_rerank      = _int("MAX_QANYTHING_CHUNKS_TO_RERANK", 10),
        max_firecrawl_qanything_chunks_to_process = _int("MAX_FIRECRAWL_QANYTHING_CHUNKS_TO_PROCESS", 10),
        min_qanything_results_before_web_search   = _int("MIN_QANYTHING_RESULTS_BEFORE_WEB_SEARCH", 2),
        max_chunks_for_summary                 = _int("MAX_CHUNKS_FOR_SUMMARY", 25),
    )

    # --- Test Scenarios ---
    log.color_print("\n\n======== TEST SCENARIO 1: Query with Web Search Only (if KB is empty or yields few results) ========\n")
    query1 = "最新的AI芯片技术有哪些进展？"
    try:
        # Override agent's search_internet default for this specific query
        final_report1, docs1, tokens1 = deep_search_agent.query(query1, search_web=True)
        # print(f"Report 1:\n{final_report1}") # The final_answer is already printed by the query method
        log.color_print(f"<main_stats_1>Tokens: {tokens1}, Retrieved Docs: {len(docs1)}</main_stats_1>\n")
    except Exception as e:
        log.color_print(f"<error_test_1>Error in test 1: {e}</error_test_1>\n")
        import traceback
        traceback.print_exc()


    log.color_print("\n\n======== TEST SCENARIO 2: Query with Local PDF and Web Search (conditional) ========\n")
    query2 = "请结合上传的Milvus文档，总结Milvus的主要特性和应用场景，并从网上查找一些最新的用户案例。"
    if os.path.exists(sample_pdf_path) and kb_id_to_use:
        try:
            final_report2, docs2, tokens2 = deep_search_agent.query(
                query2,
                files=[sample_pdf_path],
                search_web=True,
                qanything_upload_num_split_pdf=0
            )
            log.color_print(f"<main_stats_2>Tokens: {tokens2}, Retrieved Docs: {len(docs2)}</main_stats_2>\n")
        except Exception as e:
            log.color_print(f"<error_test_2>Error in test 2: {e}</error_test_2>\n")
            import traceback
            traceback.print_exc()
    else:
        log.color_print(f"<skip_test_2>Skipping Test 2: Sample PDF '{sample_pdf_path}' not found or KB ID '{kb_id_to_use}' not available.</skip_test_2>\n")


    log.color_print("\n\n======== TEST SCENARIO 3: Query with URL and No Web Search ========\n")
    query3 = "根据提供的网址内容，解释什么是向量数据库以及它的核心能力。"
    sample_url1 = "https://milvus.io/docs/overview.md"
    if firecrawl_scrape and kb_id_to_use:
        try:
            final_report3, docs3, tokens3 = deep_search_agent.query(
                query3,
                urls=[sample_url1],
                search_web=False # Explicitly disable web search for this test
            )
            log.color_print(f"<main_stats_3>Tokens: {tokens3}, Retrieved Docs: {len(docs3)}</main_stats_3>\n")
        except Exception as e:
            log.color_print(f"<error_test_3>Error in test 3: {e}</error_test_3>\n")
            import traceback
            traceback.print_exc()
    else:
        reason = []
        if not firecrawl_scrape: reason.append("firecrawl_scrape not available")
        if not kb_id_to_use: reason.append("KB ID not available")
        log.color_print(f"<skip_test_3>Skipping Test 3: {', '.join(reason)}.</skip_test_3>\n")


    log.color_print("\n\n======== TEST SCENARIO 4: Combined Query (PDF, URL, Conditional Web Search) ========\n")
    query4 = "对比分析上传的Milvus文档、指定Milvus架构概述网页以及网上关于其他向量数据库的最新信息，给出一份Milvus与其他向量数据库的综合比较报告。"
    sample_url2 = "https://milvus.io/docs/architecture_overview.md"
    if os.path.exists(sample_pdf_path) and firecrawl_scrape and kb_id_to_use:
        try:
            final_report4, docs4, tokens4 = deep_search_agent.query(
                query4,
                files=[sample_pdf_path],
                urls=[sample_url1, sample_url2], # Test with multiple URLs
                search_web=True, # Enable conditional web search
                qanything_upload_num_split_pdf=0,
                max_iter=2 # Agent default, can be overridden here
            )
            log.color_print(f"<main_stats_4>Tokens: {tokens4}, Retrieved Docs: {len(docs4)}</main_stats_4>\n")
        except Exception as e:
            log.color_print(f"<error_test_4>Error in test 4: {e}</error_test_4>\n")
            import traceback
            traceback.print_exc()
    else:
        reason = []
        if not os.path.exists(sample_pdf_path): reason.append("Sample PDF missing")
        if not firecrawl_scrape: reason.append("firecrawl_scrape not available")
        if not kb_id_to_use: reason.append("KB ID not available")
        log.color_print(f"<skip_test_4>Skipping Test 4: {', '.join(reason)}.</skip_test_4>\n")


    # --- Cleanup (Optional) ---
    if kb_id_to_use:
        try:
            # qanything_handler.delete_knowledge_base(kb_ids=[kb_id_to_use]) # Uncomment to auto-delete
            log.color_print(f"<cleanup>Consider manually deleting demo QAnything KB: {kb_name} (ID: {kb_id_to_use}) if no longer needed. Auto-delete is commented out.</cleanup>\n")
        except Exception as e:
            log.color_print(f"<cleanup_error>Error trying to delete KB {kb_id_to_use}: {e}</cleanup_error>\n")