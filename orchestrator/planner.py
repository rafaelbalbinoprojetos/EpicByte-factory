
import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

AGENT_FILE = BASE / "agents" / "orchestrator.md"
MISSION_FILE = BASE / "missions" / "mission_001.md"
OUTPUT_FILE = BASE / "missions" / "mission_001_plan.json"

CODEX = os.path.join(
    os.environ["APPDATA"], "npm", "codex.cmd"
)

def read_file(path):
    return path.read_text(encoding="utf-8")

def start_codex():
    process = subprocess.Popen(
        [CODEX, "app-server"],
        cwd=str(BASE),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )

    messages = queue.Queue()

    def read_stdout():
        for line in process.stdout:
            try:
                messages.put(json.loads(line))
            except json.JSONDecodeError:
                pass

    def read_stderr():
        for line in process.stderr:
            pass

    threading.Thread(
        target=read_stdout, daemon=True
    ).start()

    threading.Thread(
        target=read_stderr, daemon=True
    ).start()

    return process, messages

def send(process, method, params=None, request_id=None):
    message = {
        "jsonrpc": "2.0",
        "method": method,
    }

    if request_id is not None:
        message["id"] = request_id

    if params is not None:
        message["params"] = params

    process.stdin.write(
        json.dumps(message, ensure_ascii=False) + "\n"
    )
    process.stdin.flush()

def wait_response(messages, request_id, timeout=30):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try:
            message = messages.get(
                timeout=deadline - time.monotonic()
            )
        except queue.Empty:
            break

        if message.get("id") == request_id:
            return message

    raise TimeoutError(
        f"Sem resposta para requisição {request_id}"
    )

def main():
    print("EPICBYTE FACTORY — PLANNER")
    print("--------------------------")

    instructions = read_file(AGENT_FILE)
    mission = read_file(MISSION_FILE)

    prompt = f"""
    {instructions}

    MISSÃO A SER PLANEJADA:

    {mission}

    IMPORTANTE:
    Retorne somente JSON válido.
    Não utilize Markdown.
    Não implemente código.
    """

    process, messages = start_codex()

    try:
        send(process, "initialize", {
            "clientInfo": {
                "name": "epicbyte-factory",
                "title": "EpicByte Factory",
                "version": "0.1.0",
            },
            "capabilities": None,
        }, 1)

        response = wait_response(messages, 1)
        if "error" in response:
            raise RuntimeError(response["error"])

        send(process, "initialized", {})

        send(process, "thread/start", {
            "cwd": str(BASE),
            "approvalPolicy": "never",
            "sandbox": "read-only",
        }, 2)

        response = wait_response(messages, 2)
        if "error" in response:
            raise RuntimeError(response["error"])

        thread_id = response["result"]["thread"]["id"]

        print("Orquestrador analisando missão...")

        send(process, "turn/start", {
            "threadId": thread_id,
            "input": [{
                "type": "text",
                "text": prompt,
            }],
        }, 3)

        response = wait_response(messages, 3)
        if "error" in response:
            raise RuntimeError(response["error"])

        deadline = time.monotonic() + 180
        plan_text = None
        completed = False

        while time.monotonic() < deadline:
            try:
                message = messages.get(timeout=2)
            except queue.Empty:
                continue

            method = message.get("method", "")
            params = message.get("params", {})

            if method == "item/completed":
                item = params.get("item", {})
                if item.get("type") == "agentMessage":
                    plan_text = item.get("text", "")

            if method == "turn/completed":
                completed = True
                break

        if not completed:
            raise TimeoutError("Planejamento não terminou.")

        if not plan_text:
            raise RuntimeError("Nenhum plano recebido.")

        plan = json.loads(plan_text)

        OUTPUT_FILE.write_text(
            json.dumps(
                plan,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        print("\nPlano gerado com sucesso!")
        print("Arquivo:", OUTPUT_FILE)
        print("Tarefas:", len(plan.get("tasks", [])))

    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()

if __name__ == "__main__":
    main()
