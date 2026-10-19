"""Teste de resiliencia: o cliente precisa recusar inicializacao sem chave.

Uso:
    python -m tests.test_resiliencia_config
"""

import os
from unittest.mock import patch

from src.core.config import criar_cliente_gemini


def testar_falha_sem_chave() -> None:
    """Simula um clone novo sem .env: deve levantar ValueError educativo."""
    with patch.dict(os.environ, {"GEMINI_API_KEY": ""}):
        try:
            criar_cliente_gemini()
            print("FALHA: O cliente foi criado sem chave de API!")
            raise AssertionError("Cliente criado sem GEMINI_API_KEY")
        except ValueError as e:
            print("PASS: Sistema levantou ValueError educativo:", str(e))


if __name__ == "__main__":
    testar_falha_sem_chave()
