import os
import requests
import json
import time

import PyPDF2


def save_pdf_around_page_range(input_path, output_path, page_start, page_end):
    with open(input_path, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        pdf_writer = PyPDF2.PdfWriter()

        for page_num in range(page_start, page_end):
            pdf_writer.add_page(pdf_reader.pages[page_num])

        with open(output_path, 'wb') as output_file:
            pdf_writer.write(output_file)


def split_pdf_and_update_file_to_qanything(pdf_file, output_path, qanything_handler, kb_id, num_split=10):

    with open(pdf_file, 'rb') as file:
        pdf_reader = PyPDF2.PdfReader(file)
        num_pages = len(pdf_reader.pages)

    for i in range(0, num_pages, num_split):
        save_pdf_around_page_range(pdf_file, f'{output_path}/{kb_id}_{i}.pdf', i, min(i+num_split, num_pages))

        file_status = qanything_handler.upload_file(f'{output_path}/{kb_id}_{i}.pdf', kb_id=kb_id)
        qanything_handler.wait_status_to_end(kb_id, file_status['data'][0]['file_id'])

class QAnythingHandler():
    def __init__(self, server_url="http://localhost:8777", user_id="zzp"):
        """
        Initialize the QAnythingHandler with the server URL.
        :param server_url: URL of the QAnything server
        """
        self.server_url = server_url
        self.user_id = user_id

    def create_knowledge_base(self, 
                              kb_name,
                              kb_id=None,
                              quick=False):
        """
        Create a new knowledge base for the user.
        :param kb_name: Name of the knowledge base (知识库名称 （可以随意指定）)
        :param kb_id: Knowledge base ID (optional) (指定知识库id，通常用于生成FAQ知识库)
        :param quick: Whether to create a quick knowledge base (是否是快速开始模式创建的知识库，默认为False)
        :return: Response from the API

        Example:
        >>> qanything_handler = QAnythingHandler()
        >>> response = qanything_handler.create_knowledge_base("breast_cancer_kb")
        >>> print(response)

        Output:
        {'status': 'success', 'data': {'kb_id': '60f2c1f4c4b9f4f5d0d5e3d9', 'kb_name': 'breast_cancer_kb'}}
        """
        url = f"{self.server_url}/api/local_doc_qa/new_knowledge_base"
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "user_id": self.user_id,
            "kb_name": kb_name,
            "quick": quick
        }
        if kb_id:
            data["kb_id"] = kb_id

        response = requests.post(url, headers=headers, data=json.dumps(data))

        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            return {"error": str(e)}

    def list_files(self, kb_id):
        """
        List all files in the knowledge base.
        :param kb_id: Knowledge base ID

        Example:
        >>> qanything_handler = QAnythingHandler()
        >>> kb_list = qanything_handler.list_knowledge_base()
        >>> kb_id = kb_list[0]['kb_id']
        >>> files = qanything_handler.list_files(kb_id)
        >>> print(files)

        Output:
        {'status': 'success', 'data': [{'file_id': '60f2c1f4c4b9f4f5d0d5e3d9', 'file_name': 'file1.txt', 'status': 'green'}, {'file_id': '60f2c1f4c4b9f4f5d0d5e3d9', 'file_name': 'file2.txt', 'status': 'green'}]}
        """

        url = f"{self.server_url}/api/local_doc_qa/list_files"
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "user_id": self.user_id, 
            "kb_id": kb_id
        }

        response = requests.post(url, headers=headers, data=json.dumps(data))

        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            return {"error": str(e)}

    def web_to_md(self, url):
        # import requests
        # webhook_url = f'https://r.jina.ai/{url}'
        # headers = {'Accept': 'application/json'}
        # response = requests.get(webhook_url, headers=headers)

        # try:
        #     response.raise_for_status()
        #     return response.json()
        # except requests.exceptions.HTTPError as e:
        #     return {"error": str(e)}

        pass


    def upload_webpage(self, url, kb_id, output_path=None, mode="strong"):
        response = self.web_to_md(url)['data']
        if output_path is None:
            output_path = f"/tmp/{response['title'].replace(' ', '_')}.md"

        # output_path必须是md文件
        if not output_path.endswith('.md'):
            raise ValueError("Output path must be a markdown file")

        with open(output_path, 'w') as f:
            f.write(response['content'])
        return self.upload_file(output_path, kb_id, mode)

    def upload_weblink(self, url, kb_id, mode="strong", urls=[], titles=[], chunk_size=800):
        """
        Upload web links to the knowledge base.
        :param urls: List of URLs to upload
        :param kb_id: Knowledge base ID
        :param mode: Mode of the knowledge base (strong or soft)

        Example:
        >>> qanything_handler = QAnythingHandler()
        >>> kb_list = qanything_handler.list_knowledge_base()
        >>> kb_id = kb_list[0]['kb_id']
        >>> response = qanything_handler.upload_weblink("https://ai.youdao.com/DOCS", kb_id)
        >>> print(response)

        Output:
        {
            "code": 200,
            "msg": "success，后台正在飞速上传文件，请耐心等待",
            "data": [
                {
                "file_id": "9a49392e633d4c6f87e0af51e8c80a86",
                "file_name": "https://ai.youdao.com/DOCSIR

        """

        url = f"{self.server_url}/api/local_doc_qa/upload_weblink"
        data = {
            "user_id": self.user_id,
            "kb_id": kb_id,
            "mode": mode, # strong or soft
            "chunk_size": chunk_size
        }
        if urls and titles and len(urls) == len(titles):
            data["urls"] = urls
            data["titles"] = titles

        response = requests.post(url, data=data)

        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            return {"error": str(e)}


    def upload_file(self, file, kb_id, mode="strong", chunk_size=800):
        """
        Upload files to the knowledge base.
        :param files: List of files to upload
        :param kb_id: Knowledge base ID
        :param mode: Mode of the knowledge base (strong or soft)

        Example:
        >>> qanything_handler = QAnythingHandler()
        >>> kb_list = qanything_handler.list_knowledge_base()
        >>> kb_id = kb_list[0]['kb_id']
        >>> response = qanything_handler.upload_file("file1.txt", kb_id)
        >>> print(response)

        Output:
        {
            "code": 200,
            "msg": "success，后台正在飞速上传文件，请耐心等待",
            "data": [
                {
                "file_id": "9a49392e633d4c6f87e0af51e8c80a86",
                "file_name": "https://ai.youdao.com/DOCSIRMA/html/trans/api/wbfy/index.html",
                "status": "gray",
                "bytes": 0, // 网页文件无法显示大小
                "timestamp": "202401261809"
                }
            ]
        }
        """
        url = f"{self.server_url}/api/local_doc_qa/upload_files"
        data = {
            "user_id": self.user_id,
            "kb_id": kb_id,
            "mode": mode, # strong or soft
            "chunk_size": chunk_size
        }

        file_ = ("files", open(file, "rb"))

        response = requests.post(url, files=[file_], data=data, timeout=6000)

        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            return {"error": str(e)}
        
    def list_knowledge_base(self):
        """
        List all knowledge bases.
        Returns:
            List of knowledge base IDs

        Example:
        >>> qanything_handler = QAnythingHandler()
        >>> kb_list = qanything_handler.list_knowledge_base()
        >>> print(kb_list)

        Output:
        [{'kb_id': '60f2c1f4c4b9f4f5d0d5e3d9', 'kb_name': 'breast_cancer_kb'}, {'kb_id': '60f2c1f4c4b9f4f5d0d5e3d9', 'kb_name': 'diabetes_kb'}]
        """
        url = f"{self.server_url}/api/local_doc_qa/list_knowledge_base"
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "user_id": self.user_id
        }

        response = requests.post(url, headers=headers, data=json.dumps(data))

        try:
            response.raise_for_status()
            kb = response.json()
            return kb['data']
        except requests.exceptions.HTTPError as e:
            return {"error": str(e)}
    
    def list_files(self, kb_id):
        """
        List all files in the knowledge base.
        :param kb_id: Knowledge base ID

        Example:
        >>> qanything_handler = QAnythingHandler()
        >>> kb_list = qanything_handler.list_knowledge_base()
        >>> kb_id = kb_list[0]['kb_id']
        >>> files = qanything_handler.list_files(kb_id)
        >>> print(files)

        Output:
        {
            "code": 200, //状态码
            "msg": "success", //提示信息
            "data": {
                "total": {  // 知识库所有文件状态
                    "green": 100,
                    "red": 1,
                    "gray": 1,
                    "yellow": 1,
                },
                "details": {  // 每个文件的具体状态
                    {
                        "file_id": "21a9f13832594b0f936b62a54254543b", //文件id
                        "file_name": "有道知识库问答产品介绍.pptx", //文件名
                        "status": "green", //文件状态（red：入库失败-切分失败，green，成功入库，yellow：入库失败-milvus失败，gray：正在入库）
                        "bytes": 177925,
                        "content_length": 3059,  // 文件解析后字符长度，用len()计算
                        "timestamp": "202401261708",
                        "msg": "上传成功"
                    },
                    {
                        "file_id": "333e69374a8d4b9bac54f274291f313e", //文件id
                        "file_name": "网易有道智云平台产品介绍2023.6.ppt", //文件名
                        "status": "green", //文件状态（red：入库失败-切分失败，green，成功入库，yellow：入库失败-milvus失败，gray：正在入库）
                        "bytes": 12379,
                        "content_length": 3239,  // 文件解析后字符长度，用len()计算
                        "timestamp": "202401261708",
                        "msg": "上传成功"
                    }
                }
                // ...
            }
        }
        """
        url = f"{self.server_url}/api/local_doc_qa/list_files"
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "user_id": self.user_id,
            "kb_id": kb_id,
        }

        response = requests.post(url, headers=headers, data=json.dumps(data))

        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            return {"error": str(e)}

    def chat(self, 
             question, 
             kb_ids,
             history=[],
             rerank=True,
             networking=False,
             custom_prompt=None,
             only_need_search_results=False,
             source=None,
             hybrid_search=True,
             max_token=8192,
             api_base='https://api.openai.com/v1',
             api_key='sk-xxxx',
             api_context_length=32768,
             model='gpt-3.5-turbo',
             top_p=0.99,
             temperature=0.5,
             web_chunk_size=800,):
        """
        Chat with the knowledge base.
        :param question: Question to ask
        :param kb_id: Knowledge base ID list
        :param history: History of the conversation (optional)
            e.g. [["question1","answer1"],["question2","answer2"]]
        :param rerank: Whether to rerank the results (optional)
        :param networking: Whether to use the network (optional)
        :param custom_prompt: Custom prompt for the model (optional)
            e.g. "你是一个耐心、友好、专业的编程机器人，能够准确的回答用户的各种编程问题。"
        :param only_need_search_results: Whether to only return search results (optional)
        :param source (optional): Source of the request, e.g. paas, saas_bot, saas_qa. paas is for API calls, saas_bot is for front-end bot Q&A, and saas_qa is for front-end knowledge base Q&A.
        :param hybrid_search (optional): Whether to use hybrid search (optional)
        :param max_token (optional): Maximum token length for the model (optional)
        :param api_base (optional): API base URL (optional)
        :param api_key (optional): API key (optional) (default: "sk-xxxx")
        :param api_context_length (optional): API context length (optional) (default: 16000)
        :param model (optional): Model name (optional) (default: "glm4-chat-1m")
        :param top_p (optional): Top p value for the model (optional) (default: 0.99)
        :param temperature (optional): Temperature value for the model (optional) (default: 0.5)
        :param web_chunk_size (optional): Web chunk size (optional) (default: 800) 开启联网检索后生效，web搜索到的内容文本分块大小

        Example:
        >>> qanything_handler = QAnythingHandler()
        >>> kb_list = qanything_handler.list_knowledge_base()
        >>> kb_id = kb_list[0]['kb_id']
        >>> question = "What is the treatment for breast cancer?"
        >>> response = qanything_handler.chat(question, kb_id)
        >>> print(response)

        Output:
        {
            "code": 200, //状态码
            "msg": "success", //提示信息
            "question": "一嗨案件中保险单号是多少？", //用户问题
            "response": "保险单号是601J312512022000536。", //模型回答
            "history": [["一嗨案件中保险单号是多少？", "保险单号是601J312512022000536。"]], //历史对话：List[str]，至少会显示当前轮对话
            "source_documents": [
                {
                "file_id": "f9b794233c304dd5b5a010f2ead67f51", //文本内容对应的文件id
                "file_name": "一嗨案件支付三者车损、人伤保险赔款及权益转让授权书.docx", //文本内容对应的文件名
                "content": "未支付第三者车损、人伤赔款及同意直赔第三者确认书 华泰财产保险有限公司  北京   分公司： 本人租用一嗨在贵司承保车辆（车牌号：京KML920）商业险保单号： 601J312512022000536、交强险保单号:  601J310022022000570， 对 2023 年 03 月 25日所发生的保险事故（事故号：  9010020230325004124）中所涉及的交强险和商业险的保险赔款总金额 (依：三者京AFT5538定损金额)， 同意支付给本次事故中第三者方。 在此本人确认：本人从未支付给第三者方任何赔偿，且承诺不就本次事故再向贵司及一嗨进行索赔。 同时本人保证如上述内容不属实、违反承诺，造成保险人损失的，由本人承担赔偿责任。 确认人（驾驶员）签字:              第三者方签字: 联系电话：                        联系电话： 确认日期：    年    月    日", //文本内容
                "retrieval_query": "一嗨案件中保险单号是多少？", //文本内容对应的问题
                "score": "3.5585756", //相关性得分，分数越高越相关
                "embed_version": "local_v0.0.1_20230525_6d4019f1559aef84abc2ab8257e1ad4c" //embedding模型版本号
                }
            ] //知识库相关文本内容
        }
        """

        url = f'{self.server_url}/api/local_doc_qa/local_doc_chat'
        headers = {
            'content-type': 'application/json'
        }
        data = {
            "user_id": self.user_id,
            "kb_ids": kb_ids,
            "question": question,
            "rerank": rerank,
            "api_base": api_base,
            "api_key": api_key,
            "model": model,
            "hybrid_search": hybrid_search,
            "top_p": top_p,
            "temperature": temperature,
            "api_context_length": api_context_length,
            "max_token": max_token,
        }
        if history:
            data["history"] = history
        if networking:
            data["networking"] = networking
            data["web_chunk_size"] = web_chunk_size
        if custom_prompt:
            data["custom_prompt"] = custom_prompt
        if only_need_search_results:
            data["only_need_search_results"] = only_need_search_results
        if source:
            data["source"] = source

        try:
            response = requests.post(url=url, headers=headers, json=data, timeout=600)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}

    def delete_knowledge_base(self, kb_ids):
        """
        Delete knowledge base.
        :param kb_ids: List of knowledge base IDs
        """
        url = f"{self.server_url}/api/local_doc_qa/delete_knowledge_base"
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "user_id": self.user_id,
            "kb_ids": kb_ids
        }

        response = requests.post(url, headers=headers, data=json.dumps(data))

        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            return {"error": str(e)}

    def get_total_status(self):
        """
        Get the total status of the knowledge base.
        """
        url = f"{self.server_url}/api/local_doc_qa/get_total_status"
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "user_id": self.user_id
        }

        response = requests.post(url, headers=headers, data=json.dumps(data))

        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            return {"error": str(e)}


    def clean_files_by_status(self, status='gray'):
        """
        Clean files by status.
        :param status: Status of the files to clean
        """
        url = f"{self.server_url}/api/local_doc_qa/clean_files_by_status"
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "user_id": self.user_id,
            "status": status
        }

        response = requests.post(url, headers=headers, data=json.dumps(data))

        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            return {"error": str(e)}

    def delete_files(self, kb_id, file_ids):
        """
        Delete files from the knowledge base.
        :param kb_id: Knowledge base ID
        :param file_ids: List of file IDs to delete
        """
        url = f"{self.server_url}/api/local_doc_qa/delete_files"
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "user_id": self.user_id,
            "kb_id": kb_id,
            "file_ids": file_ids
        }

        response = requests.post(url, headers=headers, data=json.dumps(data))

        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            return {"error": str(e)}

    def rename_knowledge_base(self, kb_id, new_kb_name):
        """
        Rename the knowledge base.
        :param kb_id: Knowledge base ID
        :param new_kb_name: New name for the knowledge base
        """
        url = f"{self.server_url}/api/local_doc_qa/rename_knowledge_base"
        headers = {
            "Content-Type": "application/json"
        }
        data = {
            "user_id": self.user_id,
            "kb_id": kb_id,
            "new_kb_name": new_kb_name
        }

        response = requests.post(url, headers=headers, data=json.dumps(data))

        try:
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            return {"error": str(e)}

    def delete_kb_name(self, kb_name):
        try:
            kb_ids = []
            for r in self.list_knowledge_base():
                if r['kb_name'] == kb_name:
                    kb_ids.append(r['kb_id'])
                # 满10个删除一次
                if len(kb_ids) == 50:
                    self.delete_knowledge_base(kb_ids)
                    kb_ids = []
                    time.sleep(1)

            # 删除剩余的
            self.delete_knowledge_base(kb_ids)
            return kb_ids
        except Exception as e:
            return {"error": str(e)}

    def check_status(self, kb_id, file_id):
        try:
            response = self.list_files(kb_id)
            file_dict = {file['file_id']: file['status'] for file in response['data']['details']}
            file_status = file_dict[file_id]
            return file_status
        except Exception as e:
            return 'yellow'

    # def wait_status_to_end(self, kb_id, file_id, wait_time=10):
    #     while True:
    #         time.sleep(wait_time*2)
    #         file_status = self.check_status(kb_id=kb_id, file_id=file_id)
    #         if file_status in ['green', 'red']:
    #             if file_status == 'red':
    #                 time.sleep(wait_time)
    #                 self.clean_files_by_status(status='red')
    #             break
    #     return file_status

    def wait_status_to_end(self, kb_id, file_id, wait_time=10, max_wait_time=40, max_elapsed_time=300):
        increment = 0
        start_time = time.time()
        while True:
            actual_wait_time = min(wait_time + increment, max_wait_time)
            time.sleep(actual_wait_time)
            elapsed_time = time.time() - start_time
            if elapsed_time > max_elapsed_time:  # default is 5 minutes
                file_status = 'red'
                break
            file_status = self.check_status(kb_id=kb_id, file_id=file_id)
            if file_status in ['green', 'red']:
                if file_status == 'red':
                    time.sleep(actual_wait_time)
                    self.clean_files_by_status(status='red')
                break
            increment += 2
        return file_status