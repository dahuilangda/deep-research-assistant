# -*- coding: utf-8 -*-
"""
log.py

Copyright (c) 2025 <dahuilangda>
Adapted from:
    ZillizTech Deep Searcher — log utility
    https://github.com/zilliztech/deep-searcher/blob/master/deepsearcher/llm/openai_llm.py

License:
    Apache License 2.0
    https://github.com/zilliztech/deep-searcher/blob/master/LICENSE
"""

import os
import ast
import re
from abc import ABC
from typing import Dict, List


class ChatResponse(ABC):
    """
    Represents a response from a chat model.

    This class encapsulates the content of a response from a chat model
    along with information about token usage.

    Attributes:
        content: The text content of the response.
        total_tokens: The total number of tokens used in the request and response.
    """

    def __init__(self, content: str, total_tokens: int) -> None:
        """
        Initialize a ChatResponse object.

        Args:
            content: The text content of the response.
            total_tokens: The total number of tokens used in the request and response.
        """
        self.content = content
        self.total_tokens = total_tokens

    def __repr__(self) -> str:
        """
        Return a string representation of the ChatResponse.

        Returns:
            A string representation of the ChatResponse object.
        """
        return f"ChatResponse(content={self.content}, total_tokens={self.total_tokens})"


class BaseLLM(ABC):
    """
    Abstract base class for language model implementations.

    This class defines the interface for language model implementations,
    including methods for chat-based interactions and parsing responses.
    """

    def __init__(self):
        """
        Initialize a BaseLLM object.
        """
        pass

    def chat(self, messages: List[Dict]) -> ChatResponse:
        """
        Send a chat message to the language model and get a response.

        Args:
            messages: A list of message dictionaries, typically in the format
                     [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]

        Returns:
            A ChatResponse object containing the model's response.
        """
        pass

    @staticmethod
    def literal_eval(response_content: str):
        """
        Parse a string response into a Python object using ast.literal_eval.

        This method attempts to extract and parse JSON or Python literals from the response content,
        handling various formats like code blocks and special tags.

        Args:
            response_content: The string content to parse.

        Returns:
            The parsed Python object.

        Raises:
            ValueError: If the response content cannot be parsed.
        """
        response_content = response_content.strip()

        response_content = BaseLLM.remove_think(response_content)

        try:
            if response_content.startswith("```") and response_content.endswith("```"):
                if response_content.startswith("```python"):
                    response_content = response_content[9:-3]
                elif response_content.startswith("```json"):
                    response_content = response_content[7:-3]
                elif response_content.startswith("```str"):
                    response_content = response_content[6:-3]
                elif response_content.startswith("```\n"):
                    response_content = response_content[4:-3]
                else:
                    raise ValueError("Invalid code block format")
            result = ast.literal_eval(response_content.strip())
        except Exception:
            matches = re.findall(r"(\[.*?\]|\{.*?\})", response_content, re.DOTALL)

            if len(matches) != 1:
                raise ValueError(
                    f"Invalid JSON/List format for response content:\n{response_content}"
                )

            json_part = matches[0]
            return ast.literal_eval(json_part)

        return result

    @staticmethod
    def remove_think(response_content: str) -> str:
        # remove content between <think> and </think>, especial for reasoning model
        if "<think>" in response_content and "</think>" in response_content:
            end_of_think = response_content.find("</think>") + len("</think>")
            response_content = response_content[end_of_think:]
        return response_content.strip()


class OpenAI(BaseLLM):
    """
    OpenAI language model implementation.

    This class provides an interface to interact with OpenAI's language models
    through their API.

    Attributes:
        model (str): The OpenAI model identifier to use.
        client: The OpenAI client instance.
    """

    def __init__(self, model: str = "qwen3", **kwargs):
        """
        Initialize an OpenAI language model client.

        Args:
            model (str, optional): The model identifier to use. Defaults to "o1-mini".
            **kwargs: Additional keyword arguments to pass to the OpenAI client.
                - api_key: OpenAI API key. If not provided, uses OPENAI_API_KEY environment variable.
                - base_url: OpenAI API base URL. If not provided, uses OPENAI_BASE_URL environment variable.
        """
        from openai import OpenAI as OpenAI_

        self.model = model
        if "api_key" in kwargs:
            api_key = kwargs.pop("api_key")
        else:
            api_key = os.getenv("OPENAI_API_KEY")
        if "base_url" in kwargs:
            base_url = kwargs.pop("base_url")
        else:
            base_url = os.getenv("OPENAI_BASE_URL")
        self.client = OpenAI_(api_key=api_key, base_url=base_url, **kwargs)

    def chat(self, messages: List[Dict]) -> ChatResponse:
        """
        Send a chat message to the OpenAI model and get a response.

        Args:
            messages (List[Dict]): A list of message dictionaries, typically in the format
                                  [{"role": "system", "content": "..."},
                                   {"role": "user", "content": "..."}]

        Returns:
            ChatResponse: An object containing the model's response and token usage information.
        """
        completion = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=0.7,
            top_p=0.8,
        )
        return ChatResponse(
            content=completion.choices[0].message.content,
            total_tokens=completion.usage.total_tokens,
        )