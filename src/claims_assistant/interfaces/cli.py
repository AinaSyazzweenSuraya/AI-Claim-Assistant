import argparse
import json
from pathlib import Path

from claims_assistant.agent.runner import Assistant
from claims_assistant.config import Settings
from claims_assistant.rag.ingest import ingest


def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone allowance claim assistant")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("ingest", help="Build the local policy search index")
    chat = commands.add_parser("chat", help="Interactive claim preparation")
    chat.add_argument("--session", help="Resume a persisted session")
    once = commands.add_parser("ask", help="One turn; prints JSON")
    once.add_argument("message")
    once.add_argument("--session")
    once.add_argument("--revision", type=int)
    show = commands.add_parser("draft", help="Export a local draft as JSON")
    show.add_argument("id")
    serve = commands.add_parser("web", help="Start the local web app and API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    arguments = parser.parse_args()
    settings = Settings()
    settings.prepare()
    if arguments.command == "ingest":
        print(f"Indexed {ingest(settings)} policy sections")
        return
    if arguments.command == "web":
        if (
            arguments.host not in {"127.0.0.1", "localhost", "::1"}
            and settings.app_mode != "private"
        ):
            parser.error("Network exposure requires private mode and CLAIMS_API_TOKEN")
        import uvicorn

        from claims_assistant.interfaces.web import create_app

        uvicorn.run(create_app(settings), host=arguments.host, port=arguments.port)
        return
    assistant = Assistant(settings)
    if arguments.command == "draft":
        print(json.dumps(assistant.repository.draft(arguments.id), indent=2))
    elif arguments.command == "ask":
        try:
            result = assistant.respond(
                arguments.message,
                session_id=arguments.session,
                expected_revision=arguments.revision,
            )
            print(result.model_dump_json(indent=2))
        except (KeyError, ValueError) as exc:
            parser.exit(1, str(exc) + "\n")
    else:
        state = assistant.repository.load(arguments.session) if arguments.session else None
        print("Fictional MYR policy. Local drafts only. Mode: " + settings.llm_mode)
        print("Commands: /receipt PATH, /evidence-confirm, /show, business, confirm, new, /quit")
        print(
            "Enter JSON, key=value fields, or a request. "
            "Use employee_id=EMP001 to identify yourself."
        )
        while True:
            try:
                message = input("You: ").strip()
                if message == "/quit":
                    break
                if message == "/show":
                    print(state.model_dump_json(indent=2) if state else "No claim yet")
                    continue
                options = {}
                if message.startswith("/receipt "):
                    path = Path(message[9:].strip())
                    if path.stat().st_size > 20000:
                        raise ValueError("Receipt text exceeds 20,000 bytes")
                    options["receipt_text"] = path.read_text()
                    message = ""
                elif message == "/evidence-confirm":
                    options["confirm_receipt"] = True
                    message = ""
                response = assistant.respond(
                    message,
                    session_id=state.session_id if state else None,
                    expected_revision=state.revision if state else None,
                    **options,
                )
                state = response.state
                print("Assistant: " + response.message)
                if options.get("receipt_text"):
                    print(
                        state.claim.receipt.model_dump_json(indent=2)
                        if state.claim.receipt
                        else "No extraction"
                    )
                print(f"Session: {state.session_id} | {state.status} | revision {state.revision}")
            except (EOFError, KeyboardInterrupt):
                break
            except (ValueError, KeyError, OSError) as exc:
                print("Error: " + str(exc))
