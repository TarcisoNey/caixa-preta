"""Testes de resiliencia da borda da UI: entradas ruins viram ValueError tratavel (st.warning).

Uso:
    python -m tests.test_resiliencia_ui
"""

import tempfile
from pathlib import Path

from src.core.contracts import EntradaUsuario
from src.core.ingestion import despachar_ingestao


def testar_captura_de_erros_na_ui() -> None:
    """Texto so com espacos deve ser recusado ja no contrato."""
    try:
        despachar_ingestao(EntradaUsuario(tipo="texto", texto_comando="   "))
        raise AssertionError("FALHA: Entrada vazia nao levantou erro!")
    except ValueError as e:
        print("PASS: Erro capturado perfeitamente na borda:", str(e).splitlines()[0])


def testar_upload_vazio(pasta: Path) -> None:
    """Arquivos de 0 bytes (upload interrompido) devem gerar ValueError, nao travar a tela."""
    for nome, tipo in (("vazio.png", "imagem"), ("vazio.wav", "audio")):
        arquivo = pasta / nome
        arquivo.write_bytes(b"")
        try:
            despachar_ingestao(EntradaUsuario(tipo=tipo, caminho_arquivo=arquivo))
            raise AssertionError(f"FALHA: {tipo} vazio foi aceito!")
        except ValueError as e:
            print(f"PASS: {tipo} vazio recusado com aviso amigavel:", e)


if __name__ == "__main__":
    testar_captura_de_erros_na_ui()
    with tempfile.TemporaryDirectory() as tmp:
        testar_upload_vazio(Path(tmp))
