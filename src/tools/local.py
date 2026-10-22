"""Ferramentas deterministicas do OmniAssistant (SQLite local + calculos).

O catalogo simula o inventario de recursos de infraestrutura auditados pela
Squad Caixa-Preta. Toda consulta roda em modo somente leitura e com parametros.
"""

import re
import sqlite3
from contextlib import closing
from pathlib import Path

# Caminho ancorado na raiz do projeto: funciona rodando de qualquer pasta (CLI, testes, Streamlit)
DB_PATH = Path(__file__).resolve().parents[2] / "data" / "catalogo.sqlite"

# Recursos de infraestrutura sinteticos (precos em BRL; itens "(mes)" sao custo mensal)
DADOS_CATALOGO = [
    ("A101", "Sensor de Temperatura de Rack", 25.0, "Datacenter"),
    ("B202", "Cabo de Rede Blindado Cat6", 10.0, "Redes"),
    ("C303", "Instancia Cloud 4 vCPU / 16 GB (mes)", 150.0, "Cloud"),
    ("D404", "Licenca Servidor Cloud Pro", 300.0, "Software"),
    ("E505", "Bucket de Armazenamento 1 TB (mes)", 120.0, "Cloud"),
    ("F606", "Firewall Gerenciado (mes)", 450.0, "Seguranca"),
    ("G707", "Hora de Plantao de Suporte 24x7", 85.0, "Operacoes"),
    ("H808", "Disco SSD NVMe 1 TB", 520.0, "Datacenter"),
]


def inicializar_banco() -> None:
    """Cria a tabela e popula com registros sinteticos da demonstracao."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(DB_PATH)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS itens (
                codigo TEXT PRIMARY KEY,
                nome TEXT NOT NULL,
                preco REAL NOT NULL,
                setor TEXT NOT NULL
            )
        """)
        conn.executemany("INSERT OR IGNORE INTO itens VALUES (?, ?, ?, ?)", DADOS_CATALOGO)
        conn.commit()


def validar_codigo(codigo: str) -> dict:
    """Valida se o codigo segue o padrao [Letra Maiuscula][3 digitos] (ex: A101)."""
    valido = bool(re.fullmatch(r"[A-Z][0-9]{3}", codigo.strip()))
    return {"codigo": codigo, "valido": valido}


def consultar_item(codigo: str) -> dict:
    """Consulta nome, preco e setor de um recurso no banco relacional local."""
    codigo_limpo = codigo.strip().upper()
    if not validar_codigo(codigo_limpo)["valido"]:
        return {"erro": "Formato de codigo invalido. Padrao esperado: 1 letra e 3 numeros (ex: A101)."}

    if not DB_PATH.is_file():
        inicializar_banco()

    with closing(sqlite3.connect(f"{DB_PATH.as_uri()}?mode=ro", uri=True)) as conn:
        conn.execute("PRAGMA query_only = ON")
        cursor = conn.execute("SELECT codigo, nome, preco, setor FROM itens WHERE codigo = ?", (codigo_limpo,))
        linha = cursor.fetchone()

    if not linha:
        return {"encontrado": False, "mensagem": f"Item {codigo_limpo} nao consta no catalogo."}

    return {
        "encontrado": True,
        "codigo": linha[0],
        "nome": linha[1],
        "preco": linha[2],
        "setor": linha[3],
    }


def calcular_total(quantidade: float, preco_unitario: float) -> dict:
    """Calcula o valor financeiro total de um lote com precisao monetaria."""
    if quantidade <= 0 or preco_unitario < 0:
        return {"erro": "Quantidade deve ser positiva e preco nao pode ser negativo."}

    total = round(quantidade * preco_unitario, 2)
    return {
        "quantidade": quantidade,
        "preco_unitario": preco_unitario,
        "total": total,
        "moeda": "BRL",
    }


if __name__ == "__main__":
    inicializar_banco()
    print("Banco inicializado:", DB_PATH)
    print("Teste consulta A101:", consultar_item("A101"))
    print("Teste calculo 4 x 25.0:", calcular_total(4, 25.0))
