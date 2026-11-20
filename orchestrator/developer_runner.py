
import json
from pathlib import Path
from planner import start_codex, send, wait_response
import queue
import time

BASE = Path(__file__).resolve().parent.parent

PLAN_FILE = BASE / "missions" / "mission_001_plan.json"
DEVELOPER_FILE = BASE / "agents" / "developer.md"
WORKSPACE = BASE / "workspaces" / "mission_001"

TASK_ID = "TASK-001"


def main():
    plan = json.loads(
        PLAN_FILE.read_text(encoding="utf-8")
    )

    developer_instructions = DEVELOPER_FILE.read_text(
        encoding="utf-8"
    )

    task = next(
        (item for item in plan["tasks"]
         if item["id"] == TASK_ID),
        None,
    )

    if task is None:
        raise RuntimeError(f"Tarefa {TASK_ID} não encontrada")

    if task["agent"] != "developer":
        raise RuntimeError("Tarefa não pertence ao Developer")

    print("EPICBYTE FACTORY — DEVELOPER")
    print("----------------------------")
    print("Tarefa:", task["id"])
    print("Descrição:", task["description"])
    print("Workspace:", WORKSPACE)
    print("Critérios:", len(task["acceptance_criteria"]))
    print("Instruções carregadas:", bool(developer_instructions))
    
    print("Status: INICIANDO CODEX")

    process, messages = start_codex()

    try:
        send(process, "initialize", {
            "clientInfo": {
                "name": "epicbyte-developer",
                "title": "EpicByte Developer",
                "version": "0.1.0",
            },
            "capabilities": None,
        }, 1)

        response = wait_response(messages, 1)
        if "error" in response:
            raise RuntimeError(response["error"])

        send(process, "initialized", {})

        send(process, "thread/start", {
            "cwd": str(WORKSPACE),
            "approvalPolicy": "never",
            "sandbox": "read-only",
        }, 2)

        response = wait_response(messages, 2)
        if "error" in response:
            raise RuntimeError(response["error"])

        thread_id = response["result"]["thread"]["id"]

        print("Codex conectado!")
        print("Thread:", thread_id)
        print("Sandbox: read-only")

        task_prompt = f"""
{developer_instructions}

TAREFA ATRIBUÍDA:
{json.dumps(task, ensure_ascii=False, indent=2)}

WORKSPACE AUTORIZADO:
{WORKSPACE}

INSTRUÇÕES ESPECÍFICAS:
- Execute somente a TASK-001.
- Inspecione a estrutura do workspace e o estado do Git.
- Defina a arquitetura proposta para o gerenciador de tarefas.
- Não crie, edite ou exclua arquivos.
- Não execute tarefas posteriores.
- Não afirme que a implementação foi concluída.
- Apresente um relatório técnico em português.
"""

        print("Prompt da TASK-001 preparado!")
        
        
        
        send(process, "turn/start", {
            "threadId": thread_id,
            "input": [{
                "type": "text",
                "text": task_prompt,
            }],
        }, 3)

        response = wait_response(messages, 3, timeout=30)

        if "error" in response:
            raise RuntimeError(response["error"])

        print("Tarefa enviada ao Codex!")
        print("Status: EXECUÇÃO INICIADA")


        print("Aguardando relatório do Developer...")

        deadline = time.monotonic() + 180
        reports = []
        completed = False
        turn_status = None

        while time.monotonic() < deadline:
            try:
                message = messages.get(timeout=2)
            except queue.Empty:
                if process.poll() is not None:
                    raise RuntimeError(
                        "Codex encerrou antes de concluir a tarefa."
                    )
                continue

            method = message.get("method", "")
            params = message.get("params", {})

            if method == "item/completed":
                item = params.get("item", {})
                if item.get("type") == "agentMessage":
                    reports.append(item.get("text", ""))

            elif method == "turn/completed":
                turn_status = params.get("turn", {}).get("status")
                completed = True
                break

        if not completed:
            raise TimeoutError(
                "Developer não concluiu em 180 segundos."
            )

        if turn_status != "completed":
            raise RuntimeError(
                f"Turno encerrado com status: {turn_status}"
            )

        if not reports:
            raise RuntimeError(
                "Developer terminou sem relatório."
            )

        report = "\n\n".join(reports)

        
        report_file = (
            BASE / "logs" / "mission_001_task_001_developer.md"
        )

        report_file.write_text(
            report,
            encoding="utf-8",
        )

        print("Relatório salvo em:", report_file)

        
        print("\n" + "=" * 50)
        print("RELATÓRIO DO DEVELOPER — TASK-001")
        print("=" * 50)
        print(report)
        print("\nStatus: RELATÓRIO RECEBIDO")


    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except Exception:
            process.kill()
            process.wait()



if __name__ == "__main__":
    main()
