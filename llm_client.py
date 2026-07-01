"""
DeepSeek API 适配器 —— 为 mini-harness 提供真实 LLM 能力

DeepSeek API 兼容 OpenAI SDK，通过 python-dotenv 安全加载密钥。
密钥不在代码中，从 .env 文件读取（已在 .gitignore 中）。

用法:
    from llm_client import DeepSeekClient
    client = DeepSeekClient()
    reply = client.chat("你好，介绍一下自己")
"""

import os
from typing import Optional

# 尝试加载 .env（如果 python-dotenv 可用）
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass  # python-dotenv 不可用时，依赖系统环境变量


class DeepSeekClient:
    """DeepSeek API 客户端 —— 封装 chat completion 调用"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client = None

    def _get_client(self):
        """延迟初始化 OpenAI 客户端"""
        if self._client is None:
            if not self.api_key:
                raise RuntimeError(
                    "未找到 DeepSeek API Key。请在 .env 文件中设置 DEEPSEEK_API_KEY=sk-xxx"
                )
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=self.api_key,
                    base_url=self.base_url,
                )
            except ImportError:
                raise ImportError(
                    "需要 openai 包：pip install openai"
                )
        return self._client

    def chat(
        self,
        prompt: str,
        system_prompt: str = "",
        messages: Optional[list] = None,
        on_chunk: Optional[callable] = None,
    ) -> str:
        """
        发送 chat completion 请求。

        Args:
            prompt: 用户提示词（必填）
            system_prompt: 系统角色设定
            messages: 追加的历史消息列表 [{"role": "...", "content": "..."}]
            on_chunk: 流式回调 fn(text: str)，每收到一个 token 就调用。
                      提供此参数时使用流式模式，边生成边返回。

        Returns:
            LLM 的文本回复
        """
        client = self._get_client()

        api_messages = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})
        if messages:
            api_messages.extend(messages)
        api_messages.append({"role": "user", "content": prompt})

        # 流式模式
        if on_chunk:
            full = []
            try:
                stream = client.chat.completions.create(
                    model=self.model,
                    messages=api_messages,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    stream=True,
                )
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        text = chunk.choices[0].delta.content
                        full.append(text)
                        on_chunk(text)
                return "".join(full)
            except Exception as e:
                raise RuntimeError(f"DeepSeek API 流式调用失败: {e}")

        # 非流式模式
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=api_messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            raise RuntimeError(f"DeepSeek API 调用失败: {e}")

    def chat_stream(self, prompt: str, system_prompt: str = ""):
        """流式 chat completion —— 逐 token 生成"""
        client = self._get_client()

        api_messages = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})
        api_messages.append({"role": "user", "content": prompt})

        try:
            stream = client.chat.completions.create(
                model=self.model,
                messages=api_messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                stream=True,
            )
            for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            raise RuntimeError(f"DeepSeek API 流式调用失败: {e}")

    def check_connection(self) -> dict:
        """测试 API 连接，返回模型信息和余额"""
        try:
            reply = self.chat("回复 OK，不要其他内容。", system_prompt="你是一个 API 测试助手。")
            return {
                "status": "ok",
                "model": self.model,
                "base_url": self.base_url,
                "test_reply": reply.strip(),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
