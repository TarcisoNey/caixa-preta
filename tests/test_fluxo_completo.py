"""Teste integrador: EntradaUsuario -> ingestion -> evidencias -> agent -> resposta + guardrails.

Uso:
    python -m tests.test_fluxo_completo            # guardrails (offline) + fluxo completo (usa a API)
    python -m tests.test_fluxo_completo --offline  # so os guardrails, sem chamar o Gemini
"""

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path

from google.genai import types

from src.core.agent import despachar_tool, executar_agente
from src.core.contracts import EntradaUsuario
from src.core.ingestion import despachar_ingestao
from src.tools.local import DB_PATH, consultar_item, inicializar_banco

PASTA_DATA = Path(__file__).resolve().parents[1] / "data"


def _primeiro_arquivo(subpasta: str, extensoes: set[str]) -> Path | None:
    """Acha a primeira midia de demonstracao em data/<subpasta>/ (ou na raiz de data/)."""
    for pasta in (PASTA_DATA / subpasta, PASTA_DATA):
        if pasta.is_dir():
            for arquivo in sorted(pasta.iterdir()):
                if arquivo.suffix.lower() in extensoes:
                    return arquivo
    return None


def testar_pipeline_completo() -> None:
    print("Executando teste integrado de percepcao -> acao...")

    # 1. Simula as entradas do usuario
    entrada_txt = EntradaUsuario(tipo="texto", texto_comando="Identifique os itens e calcule o total")
    evidencias = [despachar_ingestao(entrada_txt)]

    # Se houver imagem ou audio em data/, adiciona ao lote
    imagem = _primeiro_arquivo("prints", {".png", ".jpg", ".jpeg"})
    audio = _primeiro_arquivo("audios", {".wav", ".mp3", ".ogg", ".m4a"})
    if imagem:
        print("Usando imagem:", imagem.name)
        evidencias.append(despachar_ingestao(EntradaUsuario(tipo="imagem", caminho_arquivo=imagem)))
    if audio:
        print("Usando audio:", audio.name)
        evidencias.append(despachar_ingestao(EntradaUsuario(tipo="audio", caminho_arquivo=audio)))

    resultado = executar_agente(entrada_txt.texto_comando, evidencias)

    assert len(resultado["resposta"]) > 10, "A resposta do modelo veio vazia!"
    print("Resposta gerada:")
    print(resultado["resposta"])
    print("\nFerramentas disparadas:", len(resultado["rastro_ferramentas"]))
    print("Tempo de execucao:", resultado["tempo_total_ms"], "ms")


def testar_guardrail_sql() -> None:
    print("\nTestando resistencia contra SQL Injection...")
    inicializar_banco()
    codigo_malicioso = "A101'; DROP TABLE itens; --"
    resultado = consultar_item(codigo_malicioso)

    assert "erro" in resultado or resultado.get("encontrado") is False
    assert consultar_item("A101")["encontrado"], "FALHA: tabela itens foi afetada!"
    print("PASS: Tentativa de SQL Injection barrada com sucesso pelo guardrail de validacao.")


def testar_banco_somente_leitura() -> None:
    """A conexao usada pelas ferramentas nao pode escrever, nem se o filtro de codigo falhar."""
    inicializar_banco()
    with closing(sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)) as conn:
        conn.execute("PRAGMA query_only = ON")
        try:
            conn.execute("DROP TABLE itens")
            raise AssertionError("FALHA: conexao somente leitura aceitou escrita!")
        except sqlite3.OperationalError as e:
            print("PASS: Escrita bloqueada na conexao somente leitura ->", e)


def testar_despachante_de_tools() -> None:
    """O despachante so executa ferramentas da allowlist e com argumentos no schema."""
    nao_autorizada = despachar_tool(types.FunctionCall(name="executar_sql", args={"sql": "DROP TABLE itens"}))
    assert "erro" in nao_autorizada, "FALHA: ferramenta fora da allowlist foi executada!"

    arg_extra = despachar_tool(types.FunctionCall(name="consultar_item", args={"codigo": "A101", "sql": "x"}))
    assert "erro" in arg_extra, "FALHA: argumento extra foi aceito!"

    fora_do_limite = despachar_tool(types.FunctionCall(
        name="calcular_total", args={"quantidade": 1_000_000.0, "preco_unitario": 25.0}
    ))
    assert "erro" in fora_do_limite, "FALHA: quantidade acima do limite foi aceita!"

    ok = despachar_tool(types.FunctionCall(name="calcular_total", args={"quantidade": 4, "preco_unitario": 25.0}))
    assert ok.get("total") == 100.0, f"FALHA: calculo inesperado {ok}"
    print("PASS: Despachante recusa ferramenta nao autorizada, argumento extra e valor fora do limite.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Roda so os guardrails, sem chamar o Gemini")
    args = parser.parse_args()

    testar_guardrail_sql()
    testar_banco_somente_leitura()
    testar_despachante_de_tools()
    if not args.offline:
        print()
        testar_pipeline_completo()
