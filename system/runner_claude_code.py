import os, json, time, datetime as dt
from pathlib import Path

from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()

BASE = Path(__file__).resolve().parent.parent
SYSTEM = BASE / "system"
TO_CLAUDE = SYSTEM / "queues" / "to_claude_code"
FROM_CLAUDE = SYSTEM / "queues" / "from_claude_code"

BRAIN = BASE
LOGS = BRAIN / "Logs"

CFG_PATH = SYSTEM / "state" / "claude_code_config.json"

ALLOWED_WRITE_ROOTS = {
    (BRAIN / "Operating").resolve(),
    (BRAIN / "Candidates").resolve(),
    (BRAIN / "Tests").resolve(),
    (BRAIN / "Logs").resolve(),
    (BRAIN / "system").resolve(),
}

DENY_EXACT = {
    (BRAIN / "README.md").resolve(),
}
DENY_ROOTS = {
    (BRAIN / "Origins").resolve(),
}

def iso_now():
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

def load_cfg():
    return json.loads(CFG_PATH.read_text(encoding="utf-8-sig"))

def read_text_safe(path: Path, max_bytes=120_000):
    data = path.read_bytes()
    if len(data) > max_bytes:
        data = data[:max_bytes]
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")

def within_allowed_write(path: Path) -> bool:
    rp = path.resolve()
    if rp in DENY_EXACT:
        return False
    for dr in DENY_ROOTS:
        try:
            rp.relative_to(dr)
            return False
        except ValueError:
            pass
    for ar in ALLOWED_WRITE_ROOTS:
        try:
            rp.relative_to(ar)
            return True
        except ValueError:
            continue
    return False

def ensure_parent(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)

def append_actions(line: str):
    LOGS.mkdir(exist_ok=True)
    (LOGS / "actions.log").open("a", encoding="utf-8").write(line.rstrip() + "\n")

def list_world_snapshot():
    out = []
    for root in sorted(ALLOWED_WRITE_ROOTS):
        if not root.exists():
            continue
        relroot = root.relative_to(BRAIN)
        for p in sorted(root.rglob("*")):
            if p.is_dir():
                continue
            try:
                rel = p.relative_to(BRAIN)
            except ValueError:
                continue
            out.append(str(rel).replace("\\", "/"))
    return out

SYSTEM_PROMPT = """You are Claude Code (Operating) acting inside a filesystem called Brain.
You must return ONLY strict JSON.

You have NO direct filesystem access. You act by emitting JSON instructions for a runner to apply.

Write permissions: only within these roots:
- Operating/
- Candidates/
- Tests/
- Logs/
- system/

Never modify:
- README.md
- anything under Origins/

If you need to see file contents before acting, return:
{"need_read":["relative/path1","relative/path2", ...]}

Otherwise return:
{
  "ops": [
    {"op":"write","path":"relative/path","content":"..."},
    {"op":"append","path":"relative/path","content":"..."},
    {"op":"mkdir","path":"relative/dir"},
    {"op":"delete","path":"relative/path"}
  ],
  "log_line":"<short action log line>"
}

Rules:
- paths are relative to Brain repo root
- do not include markdown fences
- do not include commentary outside JSON
"""

def call_claude(task_text: str, snapshot: list[str], reads: dict[str,str] | None):
    cfg = load_cfg()
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise SystemExit("ANTHROPIC_API_KEY is not set in environment.")
    client = Anthropic(api_key=key)

    user_payload = {
        "task": task_text,
        "world_files": snapshot,
        "reads": reads or {}
    }

    msg = client.messages.create(
        model=cfg["model"],
        max_tokens=cfg.get("max_tokens", 1800),
        system=SYSTEM_PROMPT,
        messages=[{"role":"user","content":json.dumps(user_payload)}]
    )
    text = msg.content[0].text
    return json.loads(text)

def apply_ops(ops: list[dict]):
    for item in ops:
        op = item.get("op")
        path_str = item.get("path","")
        if not path_str:
            raise SystemExit("Missing path in op.")
        rel = Path(path_str)
        tgt = (BRAIN / rel).resolve()

        if op == "mkdir":
            if not within_allowed_write(tgt):
                raise SystemExit(f"DENY mkdir: {rel}")
            tgt.mkdir(parents=True, exist_ok=True)

        elif op == "write":
            if not within_allowed_write(tgt):
                raise SystemExit(f"DENY write: {rel}")
            ensure_parent(tgt)
            content = item.get("content","")
            tgt.write_text(content, encoding="utf-8")

        elif op == "append":
            if not within_allowed_write(tgt):
                raise SystemExit(f"DENY append: {rel}")
            ensure_parent(tgt)
            content = item.get("content","")
            tgt.open("a", encoding="utf-8").write(content)

        elif op == "delete":
            if not within_allowed_write(tgt):
                raise SystemExit(f"DENY delete: {rel}")
            if tgt.exists() and tgt.is_file():
                tgt.unlink()

        else:
            raise SystemExit(f"Unknown op: {op}")

def run_task(task_path: Path):
    task_text = read_text_safe(task_path)
    snapshot = list_world_snapshot()
    reads = None

    for _ in range(3):
        out = call_claude(task_text, snapshot, reads)
        if "need_read" in out:
            reads = {}
            for rp in out["need_read"]:
                p = (BRAIN / rp).resolve()
                if not p.exists() or not p.is_file():
                    reads[rp] = "<missing>"
                    continue
                reads[rp] = read_text_safe(p)
            continue

        ops = out.get("ops", [])
        log_line = out.get("log_line", "claude_code_completed_task")
        apply_ops(ops)
        append_actions(f"{iso_now()} {log_line}")
        FROM_CLAUDE.mkdir(parents=True, exist_ok=True)
        done = FROM_CLAUDE / (task_path.stem + ".done")
        done.write_text(f"{iso_now()} completed {task_path.name}\n", encoding="utf-8")
        task_path.unlink()
        return

    raise SystemExit("Claude requested reads too many times.")

def main():
    tasks = sorted(TO_CLAUDE.glob("*.task"))
    if not tasks:
        print("No tasks to execute.")
        return
    run_task(tasks[0])
    print("Executed 1 task via Claude API.")

if __name__ == "__main__":
    main()
