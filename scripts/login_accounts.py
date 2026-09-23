"""
Prepara as sessões do Instaloader para as contas usadas pelo coletor,
pedindo login interativo só das contas sem sessão salva/válida.

Rode manualmente antes de iniciar o coletor (python -m src.main / docker
compose up) sempre que adicionar uma conta ou uma sessão expirar. O
coletor em si nunca pede login sozinho — só usa sessões já preparadas
aqui, pra poder rodar desacompanhado por longos períodos.

Recomendado rodar no host (Windows), não dentro do container — o Instagram
vincula a sessão ao user-agent/IP de onde ela foi criada, e criar dentro do
container é mais arriscado (ver README, seção 2).

Uso:
    python scripts/login_accounts.py
"""
import getpass
import logging
import os
import re
import sys
from pathlib import Path

import instaloader
from instaloader.exceptions import (
    BadCredentialsException,
    ConnectionException,
    LoginException,
    TwoFactorAuthRequiredException,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    """Carrega KEY=VALUE do .env para os.environ, sem sobrescrever variáveis já definidas."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip()


def _accounts() -> list[str]:
    raw = os.getenv("INSTALOADER_ACCOUNTS", "").strip()
    if raw:
        return [u.strip() for u in raw.split(",") if u.strip()]
    single = os.getenv("INSTALOADER_USERNAME", "").strip()
    return [single] if single else []


def _session_dir() -> Path:
    # INSTALOADER_SESSION_PATH é o caminho host usado no bind-mount do
    # docker-compose (ver .env.example) — mesma pasta que o container
    # enxerga como INSTALOADER_SESSION_DIR=/session.
    return Path(os.getenv("INSTALOADER_SESSION_PATH", str(PROJECT_ROOT / "session")))


def _session_file(username: str, session_dir: Path) -> str:
    return str(session_dir / f"session-{username}")


def _has_valid_session(username: str, session_dir: Path) -> bool:
    L = instaloader.Instaloader(quiet=True)
    try:
        L.load_session_from_file(username, filename=_session_file(username, session_dir))
    except FileNotFoundError:
        return False
    except Exception as e:
        log.warning(f"@{username}: erro lendo sessão existente ({e}) — tratando como inválida")
        return False
    return bool(L.test_login())


def _interactive_login(username: str, session_dir: Path) -> bool:
    L = instaloader.Instaloader(quiet=True)
    password = getpass.getpass(f"Senha para @{username}: ")
    try:
        L.login(username, password)
    except TwoFactorAuthRequiredException:
        code = input(f"Código 2FA para @{username}: ").strip()
        try:
            L.two_factor_login(code)
        except BadCredentialsException as e:
            log.error(f"@{username}: código 2FA inválido ({e})")
            return False
    except BadCredentialsException as e:
        log.error(f"@{username}: credenciais inválidas ({e})")
        return False
    except (ConnectionException, LoginException) as e:
        msg = str(e)
        if "checkpoint" in msg.lower() or "challenge" in msg.lower():
            # o Instaloader devolve o checkpoint_url cru da API, que costuma vir
            # como caminho relativo (ex: /auth_platform/?apc=...) — sem o domínio
            # não é um link válido pra colar no navegador.
            path_match = re.search(r"to (\S+) -", msg)
            path = path_match.group(1) if path_match else None
            url = f"https://www.instagram.com{path}" if path and path.startswith("/") else path
            log.error(
                f"@{username}: Instagram exigiu verificação de segurança "
                "(checkpoint) antes de permitir o login. Abra o link abaixo num "
                "navegador (de preferência já logado nessa conta), siga as "
                "instruções, e rode este script de novo"
                + (f":\n{url}" if url else f": {msg}")
            )
        else:
            log.error(f"@{username}: erro durante login ({e})")
        return False

    session_dir.mkdir(parents=True, exist_ok=True)
    filename = _session_file(username, session_dir)
    L.save_session_to_file(filename=filename)
    log.info(f"@{username}: sessão salva em {filename}")
    return True


def main() -> int:
    _load_dotenv(PROJECT_ROOT / ".env")

    accounts = _accounts()
    if not accounts:
        log.error("Nenhuma conta configurada em INSTALOADER_ACCOUNTS ou INSTALOADER_USERNAME (.env).")
        return 1
    if len(accounts) > 10:
        log.error(f"INSTALOADER_ACCOUNTS tem {len(accounts)} contas — máximo suportado é 10.")
        return 1

    session_dir = _session_dir()
    log.info(f"Verificando {len(accounts)} conta(s) em {session_dir}: {', '.join(accounts)}")

    ok, failed = [], []
    for username in accounts:
        if _has_valid_session(username, session_dir):
            log.info(f"@{username}: sessão já válida — nada a fazer")
            ok.append(username)
            continue

        log.info(f"@{username}: sessão ausente/expirada — login necessário")
        if _interactive_login(username, session_dir):
            ok.append(username)
        else:
            failed.append(username)

    log.info(f"Concluído: {len(ok)} conta(s) prontas, {len(failed)} falharam.")
    if failed:
        log.warning(f"Contas com falha: {', '.join(failed)} — o coletor vai pulá-las da rotação.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
