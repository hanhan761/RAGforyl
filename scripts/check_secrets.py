from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOKEN_PATTERNS = {
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "Aliyun AccessKey ID": re.compile(r"\bLTAI[A-Za-z0-9]{12,}\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}
ASSIGNMENT_RE = re.compile(
    r"(?m)^\s*(?:LLM_API_KEY|API_KEY|ACCESS_KEY_SECRET|SECRET_KEY|PASSWORD)\s*=\s*(.+?)\s*$"
)
SAFE_VALUES = {"", "your-api-key", "placeholder", "changeme", "example"}


def tracked_files() -> list[Path]:
    try:
        output = subprocess.check_output(
            ["git", "ls-files", "-z"],
            cwd=ROOT,
            stderr=subprocess.DEVNULL,
        )
        names = [item.decode("utf-8") for item in output.split(b"\0") if item]
        return [ROOT / name for name in names]
    except (OSError, subprocess.CalledProcessError):
        return [
            path
            for path in ROOT.rglob("*")
            if path.is_file()
            and ".git" not in path.parts
            and ".venv" not in path.parts
            and "__pycache__" not in path.parts
        ]


def main() -> None:
    findings = []
    for path in tracked_files():
        if path.name == ".env":
            findings.append(f"tracked environment file: {path.relative_to(ROOT)}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        relative = path.relative_to(ROOT)
        for label, pattern in TOKEN_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{relative}: possible {label}")
        if path.name != ".env.example":
            for match in ASSIGNMENT_RE.finditer(text):
                value = match.group(1).strip().strip("\"'")
                if value.lower() not in SAFE_VALUES and not value.startswith(
                    ("${", "os.getenv", "re.compile")
                ):
                    findings.append(f"{relative}: possible assigned secret")
    if findings:
        raise SystemExit("SECRET CHECK FAILED\n" + "\n".join(sorted(set(findings))))
    print(f"SECRET CHECK PASS | scanned={len(tracked_files())} files")


if __name__ == "__main__":
    main()
