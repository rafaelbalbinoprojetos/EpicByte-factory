
import json
import os
import queue
import subprocess
import threading
import time

CODEX = os.path.join(
    os.environ["APPDATA"], "npm", "codex.cmd"
)

process = subprocess.Popen(
    [CODEX, "app-server"],
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
        # Evita travar o processo se houver muitos logs.
        pass

threading.Thread(
    target=read_stdout, daemon=True
).start()

threading.Thread(
    target=read_stderr, daemon=True
).start()

def send(method, params=None, request_id=None):
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

def wait_response(request_id, timeout=30):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        try:
            message = messages.get(timeout=remaining)
        except queue.Empty:
            break

        if message.get("id") == request_id:
            return message

    raise TimeoutError(
        f"Sem resposta para requisição {request_id}"
    )

try:
    print("1. Inicializando Codex...")

    send("initialize", {
        "clientInfo": {
            "name": "epicbyte-factory",
            "title": "EpicByte Factory",
            "version": "0.1.0"
        },
        "capabilities": None
    }, 1)

    result = wait_response(1)
    if "error" in result:
        raise RuntimeError(result["error"])

    send("initialized", {})

    print("2. Criando sessão...")

    send("thread/start", {
        "cwd": os.getcwd(),
        "approvalPolicy": "never",
        "sandbox": "read-only"
    }, 2)

    result = wait_response(2)
    if "error" in result:
        raise RuntimeError(result["error"])

    thread_id = result["result"]["thread"]["id"]
    print("Sessão criada com sucesso.")

    print("3. Enviando instrução...")

    send("turn/start", {
        "threadId": thread_id,
        "input": [{
            "type": "text",
            "text": (
                "Responda somente com a frase: "
                "EPICBYTE FACTORY ONLINE"
            )
        }]
    }, 3)

    result = wait_response(3, timeout=30)
    if "error" in result:
        raise RuntimeError(result["error"])

    print("4. Aguardando resposta do modelo...")

    deadline = time.monotonic() + 120
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
                print("\nRESPOSTA DO CODEX:")
                print(item.get("text", ""))

        if method == "turn/completed":
            print("\nExecução finalizada.")
            completed = True
            break

    if not completed:
        print("Tempo limite atingido.")

finally:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
