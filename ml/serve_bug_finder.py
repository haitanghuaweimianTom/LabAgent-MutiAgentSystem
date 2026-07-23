"""Bug Finder Model API Server

轻量 FastAPI 服务，加载 Qwen2.5-Coder-1.5B + LoRA adapter，
提供 OpenAI 兼容的 /v1/chat/completions 接口。

启动方式：
    cd /home/tomgame/projects/MathModel-MutiAgentSystem
    python ml/serve_bug_finder.py

默认端口 8100，可通过 BUG_FINDER_PORT 环境变量修改。
"""
import os
import sys
import json
import time
import logging
from pathlib import Path
from typing import List, Optional

# 在导入其他模块前清除代理环境变量（与 app/main.py 一致）
for var in ("ALL_PROXY", "all_proxy", "HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy"):
    os.environ.pop(var, None)

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("bug_finder_server")

app = FastAPI(title="Bug Finder Model API", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ---------- 模型配置 ----------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
BASE_MODEL_PATH = str(PROJECT_ROOT / "ml" / "models" / "qwen2.5-coder-1.5b-instruct")
ADAPTER_PATH = str(PROJECT_ROOT / "ml" / "checkpoints" / "bug_finder_qlora")

# ---------- 全局状态 ----------
model = None
tokenizer = None
model_loaded = False
load_time_ms = 0


# ---------- 请求/响应模型 ----------
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = "bug-finder"
    messages: List[ChatMessage]
    temperature: float = 0.1
    max_tokens: int = 512
    stream: bool = False


class ChatChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatChoice]
    usage: Usage


# ---------- 模型加载 ----------
def load_model():
    global model, tokenizer, model_loaded, load_time_ms

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    logger.info(f"加载 base model: {BASE_MODEL_PATH}")
    t0 = time.time()

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_PATH, trust_remote_code=True)

    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_PATH,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True,
    )

    logger.info(f"加载 LoRA adapter: {ADAPTER_PATH}")
    model = PeftModel.from_pretrained(model, ADAPTER_PATH)
    model.eval()

    load_time_ms = (time.time() - t0) * 1000
    model_loaded = True
    logger.info(f"模型加载完成，耗时 {load_time_ms:.0f}ms")

    # 打印显存占用
    if torch.cuda.is_available():
        mem = torch.cuda.memory_allocated() / 1024**3
        logger.info(f"GPU 显存占用: {mem:.2f} GB")


# ---------- API 端点 ----------
@app.get("/health")
async def health():
    return {"status": "ok", "model_loaded": model_loaded, "load_time_ms": load_time_ms}


@app.post("/v1/chat/completions")
async def chat_completions(req: ChatCompletionRequest):
    if not model_loaded:
        raise HTTPException(status_code=503, detail="Model not loaded yet")

    import torch

    # 构建 prompt
    system_msg = ""
    user_msg = ""
    for msg in req.messages:
        if msg.role == "system":
            system_msg = msg.content
        elif msg.role == "user":
            user_msg = msg.content

    # 使用 tokenizer 的 chat template
    messages = []
    if system_msg:
        messages.append({"role": "system", "content": system_msg})
    messages.append({"role": "user", "content": user_msg})

    text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    inputs = tokenizer(text, return_tensors="pt").to(model.device)

    t0 = time.time()
    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=req.max_tokens,
            temperature=req.temperature,
            do_sample=req.temperature > 0,
            top_p=0.95,
            pad_token_id=tokenizer.eos_token_id,
        )
    latency_ms = (time.time() - t0) * 1000

    # 只取新生成的 token
    generated = outputs[0][inputs["input_ids"].shape[1]:]
    response_text = tokenizer.decode(generated, skip_special_tokens=True)

    prompt_tokens = inputs["input_ids"].shape[1]
    completion_tokens = len(generated)

    logger.info(f"推理完成: {prompt_tokens}→{completion_tokens} tokens, {latency_ms:.0f}ms")

    return ChatCompletionResponse(
        id=f"chatcmpl-bugfinder-{int(time.time())}",
        created=int(time.time()),
        model=req.model,
        choices=[ChatChoice(message=ChatMessage(role="assistant", content=response_text))],
        usage=Usage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens),
    )


@app.get("/v1/models")
async def list_models():
    return {
        "data": [{"id": "bug-finder", "object": "model", "owned_by": "local"}]
    }


# ---------- 启动 ----------
if __name__ == "__main__":
    # 后台加载模型（不阻塞 uvicorn 启动）
    import threading
    threading.Thread(target=load_model, daemon=True).start()

    port = int(os.environ.get("BUG_FINDER_PORT", "8100"))
    logger.info(f"启动 Bug Finder API 服务: http://0.0.0.0:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
