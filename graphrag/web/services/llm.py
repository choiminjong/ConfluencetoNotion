"""LLM + Embedding 어댑터.

AWS Bedrock (Claude)과 Azure OpenAI Embedding을 neo4j_graphrag 인터페이스에 맞춰 제공한다.
"""

import os

import anthropic
import httpx
from neo4j_graphrag.embeddings.openai import BaseOpenAIEmbeddings
from neo4j_graphrag.llm.base import LLMInterface
from neo4j_graphrag.llm.types import LLMResponse, ToolCall, ToolCallResponse


class BedrockLLM(LLMInterface):
    """AWS Bedrock (Anthropic Claude) 기반 LLM."""

    def __init__(self, model_name, model_params=None, region=None):
        super().__init__(model_name=model_name, model_params=model_params)
        self.client = anthropic.AnthropicBedrock(
            aws_region=region or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        )

    def invoke(self, input, message_history=None, system_instruction=None):
        msgs = list(message_history or []) + [{"role": "user", "content": input}]
        r = self.client.messages.create(
            model=self.model_name,
            messages=msgs,
            system=system_instruction or anthropic.NOT_GIVEN,
            **self.model_params,
        )
        return LLMResponse(content=r.content[0].text)

    async def ainvoke(self, input, message_history=None, system_instruction=None):
        return self.invoke(input, message_history, system_instruction)

    def invoke_with_tools(self, input, tools, message_history=None, system_instruction=None):
        anthropic_tools = [
            {
                "name": t.get_name(),
                "description": t.get_description(),
                "input_schema": t.get_parameters() or {"type": "object", "properties": {}},
            }
            for t in tools
        ]
        msgs = list(message_history or []) + [{"role": "user", "content": input}]
        r = self.client.messages.create(
            model=self.model_name,
            messages=msgs,
            tools=anthropic_tools,
            system=system_instruction or anthropic.NOT_GIVEN,
            **self.model_params,
        )
        calls = [
            ToolCall(name=b.name, arguments=b.input or {})
            for b in r.content
            if b.type == "tool_use"
        ]
        text = next((b.text for b in r.content if b.type == "text"), None)
        return ToolCallResponse(tool_calls=calls, content=text)


class AzureOpenAIEmbeddings(BaseOpenAIEmbeddings):
    """Azure OpenAI 기반 Embeddings."""

    def _initialize_client(self, **kwargs):
        return self.openai.AzureOpenAI(
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01"),
            http_client=httpx.Client(verify=False),
        )
