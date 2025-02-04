import os
import random
import time
import threading

from fastapi import FastAPI, HTTPException
import httpx
import uvicorn

from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry import trace
from opentelemetry.trace import (
    SpanKind,
    get_tracer_provider,
    set_tracer_provider,
)
from opentelemetry.propagate import extract
from logging import getLogger


import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, pipeline
from dotenv import load_dotenv

from models import Choice, CompletionRequest, CompletionResponse, Message


load_dotenv()
conn_str = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
if not conn_str:
    raise ValueError(
        "No connection string for Azure Monitor found. Please set the APPLICATIONINSIGHTS_CONNECTION_STRING environment variable.")


configure_azure_monitor(
    connection_string=conn_str,
    enable_live_metrics=True,
)

app = FastAPI()
tracer = trace.get_tracer(__name__,
                          tracer_provider=get_tracer_provider())
logger = getLogger(__name__)
FastAPIInstrumentor.instrument_app(app)


start_time = time.time()
torch.random.manual_seed(0)
MODEL = "microsoft/Phi-3.5-mini-instruct"
model = AutoModelForCausalLM.from_pretrained(
    MODEL,
    device_map="cuda",
    torch_dtype="auto",
    trust_remote_code=True,
)
tokenizer = AutoTokenizer.from_pretrained(MODEL)
end_time = time.time()
logger.info(f"Model {MODEL} loading time: {end_time - start_time} seconds")

pipe = pipeline(
    "text-generation",
    model=model,
    tokenizer=tokenizer,
)


def test_pipeline():
    generation_args = {
        "max_new_tokens": 500,
        "return_full_text": False,
        "temperature": 0.0,
        "do_sample": False,
    }
    messages = [
        {"role": "system", "content": "You are a helpful AI assistant."},
        {"role": "user", "content": "Can you provide ways to eat combinations of bananas and dragonfruits?"},
        {"role": "assistant", "content": "Sure! Here are some ways to eat bananas and dragonfruits together: 1. Banana and dragonfruit smoothie: Blend bananas and dragonfruits together with some milk and honey. 2. Banana and dragonfruit salad: Mix sliced bananas and dragonfruits together with some lemon juice and honey."},
        {"role": "user", "content": "What about solving an 2x + 3 = 7 equation?"},
    ]
    output = pipe(messages, **generation_args)
    print(output[0]['generated_text'])


@app.post("/completion", response_model=CompletionResponse)
async def post_completion(request: CompletionRequest):
    rval = random.random()
    # return random failures
    if rval < 0.2:
        raise HTTPException(status_code=429, detail="Too Many Requests")
    if rval > 0.95:
        raise HTTPException(status_code=500, detail="Internal Server Error")

    logger.info(f"Processing request")
    # process the request
    generation_args = {
        "max_new_tokens": request.max_new_tokens,
        "return_full_text": False,
        "temperature": request.temperature,
        "do_sample": False,
    }
    messages = [{"role": message.role, "content": message.content}
                for message in request.messages]
    output = pipe(messages, **generation_args)
    # return {"response": output[0]['generated_text']}
    return CompletionResponse(choices=[Choice(text=output[0]['generated_text'], index=0)])


@app.get("/status")
def status():
    return {"status": "ok"}


def task():
    time.sleep(5)
    payload: CompletionRequest = None
    while True:
        try:
            payload = CompletionRequest(
                messages=[Message(role="user", content="What is 2+2?"),])
            print("Sending request")
            r = httpx.post("http://localhost:8000/completion",
                           data=payload.model_dump_json())
            print(r.json())
        except Exception as e:
            pass


if __name__ == "__main__":
    background_thread = threading.Thread(target=task)
    background_thread.start()

    uvicorn.run(app, host="0.0.0.0", port=8000)
