"""Apply non-secret production security defaults without printing .env values."""
from pathlib import Path
import os


path = Path(".env")
updates = {
    "APP_ENV": "production",
    "APP_DEBUG": "false",
    "ALLOWED_ORIGINS": "https://adimax.jmtransportes.tech",
    "API_RATE_LIMIT": "300/minute",
}
lines = path.read_text(encoding="utf-8").splitlines()
seen: set[str] = set()
result: list[str] = []
for line in lines:
    key = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else ""
    if key in updates:
        result.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        result.append(line)
for key, value in updates.items():
    if key not in seen:
        result.append(f"{key}={value}")

temporary = path.with_suffix(".env.security-tmp")
temporary.write_text("\n".join(result) + "\n", encoding="utf-8")
os.chmod(temporary, path.stat().st_mode)
temporary.replace(path)
print("Configuração de produção reforçada.")
