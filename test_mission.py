
import json
import os
import queue
import subprocess
import threading
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent
WORKSPACE = BASE / "sandbox_mission"
WORKSPACE.mkdir(exist_ok=True)

CODEX = os.path.join(
    os.environ["APPDATA"], "npm", "codex.cmd"
)

process = subprocess.Popen(
    [CODEX, "app-server"],
    cwd=str(WORKSPACE),
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

    print("2. Criando sessão com escrita controlada...")

    send("thread/start", {
        "cwd": str(WORKSPACE),
        "approvalPolicy": "never",
        "sandbox": "workspace-write"
    }, 2)

    result = wait_response(2)
    if "error" in result:
        raise RuntimeError(result["error"])

    thread_id = result["result"]["thread"]["id"]

    print("3. Enviando primeira missão...")

    mission = """
    Você está executando uma missão de teste
    da EpicByte Factory.

    Objetivo:
    Criar um arquivo chamado calculadora.py.

    Requisitos:
    - Implementar uma função somar(a, b).
    - Implementar uma função multiplicar(a, b).
    - Criar um arquivo test_calculadora.py.
    - Utilizar unittest da biblioteca padrão.
    - Criar pelo menos 4 testes.
    - Executar os testes.
    - Corrigir eventuais erros.

    Trabalhe somente no diretório atual.
    Não instale dependências.
    Não altere arquivos fora do workspace.

    Ao finalizar, informe:
    - Arquivos criados.
    - Quantidade de testes executados.
    - Resultado dos testes.
    """

    send("turn/start", {
        "threadId": thread_id,
        "input": [{
            "type": "text",
            "text": mission
        }]
    }, 3)

    result = wait_response(3)
    if "error" in result:
        raise RuntimeError(result["error"])

    print("4. Codex trabalhando...\n")

    deadline = time.monotonic() + 180
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
                print("\nCODEX:")
                print(item.get("text", ""))

        if method == "turn/completed":
            print("\nMissão finalizada pelo Codex.")
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

print("\n5. Verificando arquivos criados...")

for filename in [
    "calculadora.py",
    "test_calculadora.py"
]:
    path = WORKSPACE / filename
    print(
        filename,
        "OK" if path.exists() else "NÃO ENCONTRADO"
    )

print("\nWorkspace:", WORKSPACE)
