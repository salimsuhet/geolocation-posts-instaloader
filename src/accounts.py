"""
Rotação entre múltiplas contas do Instagram e janela de horário de coleta.

Contas: lista em INSTALOADER_ACCOUNTS (fallback: INSTALOADER_USERNAME única).
Cada conta precisa ter sessão salva previamente via `scripts/login_accounts.py`
em INSTALOADER_SESSION_DIR (arquivo session-<username>) — este módulo nunca
pede login interativo, só carrega sessões já existentes.
"""
import logging
import os
import random
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .config import (
    ACCOUNT_ROTATE_MAX_HOURS,
    ACCOUNT_ROTATE_MIN_HOURS,
    COLLECT_WINDOW_DAYS,
    COLLECT_WINDOW_END,
    COLLECT_WINDOW_START,
    COLLECT_WINDOW_TZ,
    INSTALOADER_SESSION_DIR,
)

log = logging.getLogger(__name__)

_TZ = ZoneInfo(COLLECT_WINDOW_TZ)


def _session_file(username: str) -> str | None:
    if not INSTALOADER_SESSION_DIR:
        return None
    return os.path.join(INSTALOADER_SESSION_DIR, f"session-{username}")


class AccountRotator:
    """
    Mantém qual conta está ativa na sessão do Instaloader (L) e troca para
    outra periodicamente (janela sorteada entre ACCOUNT_ROTATE_MIN_HOURS e
    ACCOUNT_ROTATE_MAX_HOURS).

    maybe_rotate(L) só deve ser chamado em pontos "seguros" do loop principal
    (entre locations/hashtags/pontos da grade, nunca no meio de um item).
    """

    def __init__(self, usernames: list[str]):
        if not usernames:
            raise ValueError(
                "Nenhuma conta configurada (INSTALOADER_ACCOUNTS ou INSTALOADER_USERNAME)."
            )
        self._all = list(usernames)
        self._unavailable: set[str] = set()
        self.active: str | None = None
        self._rotate_at: datetime | None = None

    @property
    def _available(self) -> list[str]:
        pool = [u for u in self._all if u not in self._unavailable]
        # se todas foram marcadas indisponíveis nesta rodada, tenta de novo do zero
        return pool or list(self._all)

    def _schedule_next_rotation(self) -> None:
        hours = random.uniform(ACCOUNT_ROTATE_MIN_HOURS, ACCOUNT_ROTATE_MAX_HOURS)
        self._rotate_at = datetime.now(_TZ) + timedelta(hours=hours)
        log.info(
            f"Próxima rotação de conta em ~{hours:.1f}h "
            f"(por volta de {self._rotate_at:%Y-%m-%d %H:%M})"
        )

    def _pick_next(self) -> str:
        candidates = [u for u in self._available if u != self.active] or self._available
        return random.choice(candidates)

    def _try_load(self, L, username: str) -> bool:
        try:
            L.load_session_from_file(username, filename=_session_file(username))
        except FileNotFoundError:
            log.warning(
                f"Sem sessão salva para @{username} — pulando da rotação "
                "(rode scripts/login_accounts.py)"
            )
            self._unavailable.add(username)
            return False
        except Exception as e:
            log.warning(f"Falha ao carregar sessão de @{username}: {e} — pulando da rotação")
            self._unavailable.add(username)
            return False

        if not L.test_login():
            log.warning(
                f"Sessão de @{username} inválida/expirada — pulando da rotação "
                "(rode scripts/login_accounts.py)"
            )
            self._unavailable.add(username)
            return False

        self.active = username
        self._unavailable.discard(username)
        log.info(f"Conta ativa: @{username}")
        return True

    def ensure_active(self, L) -> bool:
        """Garante que há uma conta carregada em L. Chamar antes de começar a coletar."""
        if self.active is not None:
            return True
        for _ in range(len(self._all)):
            candidate = self._pick_next()
            if self._try_load(L, candidate):
                self._schedule_next_rotation()
                return True
        log.error(
            "Nenhuma conta com sessão válida disponível — coleta seguirá sem login "
            "(rate limit mais agressivo)"
        )
        return False

    def maybe_rotate(self, L) -> None:
        """Chamar entre unidades de trabalho (location/hashtag/ponto da grade)."""
        if self._rotate_at is None:
            self.ensure_active(L)
            return
        if datetime.now(_TZ) < self._rotate_at:
            return

        for _ in range(len(self._all)):
            candidate = self._pick_next()
            if self._try_load(L, candidate):
                self._schedule_next_rotation()
                return
        log.warning("Nenhuma conta alternativa disponível para rotação — mantendo conta atual")
        self._schedule_next_rotation()

    def current_cookie_header(self, L) -> str:
        """Cookie da sessão ativa, formato 'k=v; k2=v2' (usado pelos requests manuais do geo_grid)."""
        jar = L.context._session.cookies
        return "; ".join(f"{k}={v}" for k, v in jar.get_dict().items())


def is_within_window(now: datetime | None = None) -> bool:
    """True se `now` (ou o instante atual) está dentro da janela configurada."""
    if COLLECT_WINDOW_START is None:
        return True
    now = (now or datetime.now(_TZ)).astimezone(_TZ)
    if now.weekday() not in COLLECT_WINDOW_DAYS:
        return False
    current = now.time()
    if COLLECT_WINDOW_START <= COLLECT_WINDOW_END:
        return COLLECT_WINDOW_START <= current <= COLLECT_WINDOW_END
    # janela que cruza a meia-noite (ex: 22:00-06:00)
    return current >= COLLECT_WINDOW_START or current <= COLLECT_WINDOW_END


def wait_for_window(check_interval: int = 300) -> None:
    """Bloqueia até entrar na janela configurada. Não faz nada se não houver restrição."""
    if COLLECT_WINDOW_START is None:
        return
    logged = False
    while not is_within_window():
        if not logged:
            now = datetime.now(_TZ)
            log.info(
                f"Fora da janela de coleta ({now:%a %H:%M} {COLLECT_WINDOW_TZ}) — "
                f"aguardando até {COLLECT_WINDOW_START.strftime('%H:%M')}"
            )
            logged = True
        time.sleep(check_interval)
    if logged:
        log.info("Dentro da janela de coleta — retomando")
