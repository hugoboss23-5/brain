import datetime as dt
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CANDIDATES = BASE / 'Candidates'
OUT = BASE / 'Logs' / 'candidates'

def iso_now():
    return dt.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for p in sorted(CANDIDATES.glob('*.md')):
        if p.name == '_about.md':
            continue
        report = OUT / f"{p.stem}_report.md"
        report.write_text(
            f"# Candidate Report: {p.name}\n\n"
            f"Generated: {iso_now()}\n\n"
            "## Opus critique (read-only)\n\n"
            "(paste Opus analysis here)\n\n"
            "## Claude Code execution plan (write)\n\n"
            "(Claude Code proposes how to realize this candidate safely)\n",
            encoding='utf-8'
        )
    print('OK')

if __name__ == '__main__':
    main()
