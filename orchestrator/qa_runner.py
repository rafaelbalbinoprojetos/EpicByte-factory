
import json
from pathlib import Path
from planner import start_codex, send, wait_response
import queue
import time

BASE = Path(__file__).resolve().parent.parent

PLAN_FILE = BASE / "missions" / "mission_001_plan.json"
QA_FILE = BASE / "agents" / "qa.md"
DEVELOPER_REPORT = (
    BASE / "logs" / "mission_001_task_001_developer.md"
)
WORKSPACE = BASE / "workspaces" / "mission_001"

TASK_ID = "TASK-001"


def main():
    plan = json.loads(
        PLAN_FILE.read_text(encoding="utf-8")
    )

    task = next(
        (item for item in plan["tasks"]
         if item["id"] == TASK_ID),
        None,
    )

    if task is None:
        raise RuntimeError("Tarefa não encontrada")

    qa_instructions = QA_FILE.read_text(
        encoding="utf-8"
    )

    developer_report = DEVELOPER_REPORT.read_text(
        encoding="utf-8"
    )

    print("EPICBYTE FACTORY — QA")
    print("---------------------")
    print("Tarefa:", task["id"])
    print("Critérios:", len(task["acceptance_criteria"]))
    print("Workspace:", WORKSPACE)
    print("Instruções QA:", bool(qa_instructions))
    print("Relatório Developer:", bool(developer_report))
    print("Status: PRONTO PARA AUDITORIA")

    
    print("Status: INICIANDO CODEX QA")

    process, messages = start_codex()

    try:
        send(process, "initialize", {
            "clientInfo": {
                "name": "epicbyte-qa",
                "title": "EpicByte QA",
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

        print("QA conectado ao Codex!")
        print("Thread:", thread_id)
        print("Sandbox: read-only")
        
        
        qa_prompt = f"""
{qa_instructions}

TAREFA A SER AUDITADA:
{json.dumps(task, ensure_ascii=False, indent=2)}

RELATÓRIO DO DEVELOPER:
{developer_report}

WORKSPACE AUTORIZADO:
{WORKSPACE}

INSTRUÇÕES DA AUDITORIA:
- Audite exclusivamente a TASK-001.
- Verifique independentemente o estado do Git.
- Confira a estrutura real do workspace.
- Avalie individualmente os cinco critérios de aceite.
- Não aceite declarações sem evidências.
- Não crie, modifique ou exclua arquivos.
- Não implemente tarefas posteriores.
- Classifique cada critério como APROVADO,
  REPROVADO ou BLOQUEADO.
- Emita um parecer final fundamentado em português.
"""

        print("Prompt da auditoria preparado!")
        print("Caracteres:", len(qa_prompt))

        
        send(process, "turn/start", {
            "threadId": thread_id,
            "input": [{
                "type": "text",
                "text": qa_prompt,
            }],
        }, 3)

        response = wait_response(messages, 3, timeout=30)

        if "error" in response:
            raise RuntimeError(response["error"])

        print("Auditoria iniciada. Aguardando QA...")

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
                        "Codex encerrou antes de concluir."
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
                "QA não concluiu em 180 segundos."
            )

        if turn_status != "completed":
            raise RuntimeError(
                f"Auditoria encerrada com status: {turn_status}"
            )

        if not reports:
            raise RuntimeError("QA terminou sem relatório.")

        report = "\n\n".join(reports)

        report_file = (
            BASE / "logs" / "mission_001_task_001_qa.md"
        )

        report_file.write_text(
            report,
            encoding="utf-8",
        )

        print("\n" + "=" * 50)
        print("RELATÓRIO DO QA — TASK-001")
        print("=" * 50)
        print(report)
        print("\nRelatório salvo em:", report_file)
        print("Status: AUDITORIA FINALIZADA")


    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except Exception:
            process.kill()
            process.wait()


if __name__ == "__main__":
    main()
