"""Configuracao centralizada do OmniAssistant.

Unico lugar do projeto que le segredos e parametros de API. Os demais modulos
(vision, audio, tools, app) importam daqui em vez de ler o ambiente direto.
"""

import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

# Carrega o .env (se existir) logo na importacao; nao sobrescreve variaveis ja definidas.
load_dotenv()

NOME_SQUAD = "Caixa-Preta"
DOMINIO = "Auditoria de Infraestrutura e TI (prints de cloud + audios de incidentes)"

MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash").strip() or "gemini-3.8-flash"
TIMEOUT_MS = 30_000

# Modelo local do Whisper: "tiny" erra muito em portugues; "small" acerta termos tecnicos
# e numeros (~1-2s por audio curto em CPU). Opcoes: tiny, base, small, medium.
WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small").strip() or "small"


def criar_cliente_gemini() -> genai.Client:
    """Carrega as variaveis de ambiente e instancia o cliente oficial com timeout estrito.

    Returns:
        Cliente do Gemini pronto para uso.

    Raises:
        ValueError: Se GEMINI_API_KEY nao estiver definida (ou estiver vazia).
    """
    load_dotenv()
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError(
            "Chave GEMINI_API_KEY ausente! Copie .env.example para .env e preencha a chave, "
            "ou configure a variavel no ambiente."
        )

    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=TIMEOUT_MS),
    )


def chave_configurada() -> bool:
    """Informa se ha GEMINI_API_KEY no ambiente, sem expor o valor (usado pela UI)."""
    return bool(os.environ.get("GEMINI_API_KEY", "").strip())


def obter_status_configuracao(nome_squad: str = NOME_SQUAD) -> str:
    """Resume a configuracao ativa sem expor a chave de API.

    Args:
        nome_squad: Nome da squad exibido no status.

    Returns:
        Linha de status com squad, modelo, timeout e se a chave esta presente.
    """
    status_chave = "configurada" if chave_configurada() else "AUSENTE"
    return (
        f"Squad '{nome_squad}' | Dominio: {DOMINIO} | Modelo: {MODEL} | "
        f"Timeout: {TIMEOUT_MS}ms | GEMINI_API_KEY: {status_chave}"
    )


if __name__ == "__main__":
    print(obter_status_configuracao())
    print("Configuracao centralizada carregada com sucesso!")
