"""Testes offline da camada visual (src/ui): registro, forma de onda, componentes e relatorio.

Uso:
    python -m tests.test_ui_componentes
"""

import wave
from datetime import datetime
from io import BytesIO

import numpy as np

from src.core.contracts import EvidenciaMultimodal, SegmentoFala
from src.ui import componentes as ui
from src.ui.midia import calcular_forma_de_onda
from src.ui.registro import RegistroEvidencias, chave_do_arquivo
from src.ui.relatorio import gerar_relatorio


def _wav(segundos: float = 3.0, taxa: int = 16_000) -> bytes:
    t = np.arange(int(segundos * taxa)) / taxa
    sinal = (0.4 * np.sin(2 * np.pi * 220 * t) * (t % 1.0)).astype(np.float32)
    buffer = BytesIO()
    with wave.open(buffer, "wb") as arquivo:
        arquivo.setnchannels(1)
        arquivo.setsampwidth(2)
        arquivo.setframerate(taxa)
        arquivo.writeframes((sinal * 32767).astype(np.int16).tobytes())
    return buffer.getvalue()


def _evidencia_audio() -> EvidenciaMultimodal:
    return EvidenciaMultimodal(
        origem="audio",
        resumo_informacao="CPU em 92% desde o deploy.",
        segmentos_audio=[SegmentoFala(inicio_segundos=1.0, fim_segundos=2.0, texto_transcrito="CPU em 92%")],
    )


def testar_registro() -> None:
    """Mesmo arquivo reaproveita o ID; arquivo novo ganha o proximo; limpar zera a contagem."""
    registro = RegistroEvidencias()
    dados = _wav()
    chave, sha = chave_do_arquivo("audio", dados)
    campos = dict(nome="relato.wav", tipo="audio", sha256=sha, dados=dados, evidencia=_evidencia_audio(), canal="chat")
    primeiro = registro.registrar(chave, **campos)
    assert registro.registrar(chave, **campos) is primeiro and primeiro.id == "E01"
    outro_chave, outro_sha = chave_do_arquivo("audio", dados + b"\0")
    assert registro.registrar(outro_chave, **{**campos, "sha256": outro_sha}).id == "E02"
    assert registro.por_id("E02") is not None and len(registro) == 2
    registro.limpar()
    assert len(registro) == 0
    print("PASS: registro mantem IDs estaveis e cache por hash")


def testar_forma_de_onda() -> None:
    """WAV vira 160 barras normalizadas; bytes invalidos nao derrubam a tela (None)."""
    onda = calcular_forma_de_onda(_wav(3.0), "relato.wav")
    assert onda is not None and len(onda.picos) == 160
    assert abs(onda.duracao_segundos - 3.0) < 0.01 and max(onda.picos) == 1.0 and min(onda.picos) >= 0.08
    assert calcular_forma_de_onda(b"isto nao e audio", "quebrado.wav") is None
    print("PASS: forma de onda calculada (e ausente para audio invalido)")


def testar_componentes() -> None:
    """Texto externo e escapado, o trecho vinculado e destacado e os cifroes nao viram LaTeX."""
    registro = RegistroEvidencias()
    dados = _wav()
    chave, sha = chave_do_arquivo("audio", dados)
    item = registro.registrar(
        chave, nome="<script>x</script>.wav", tipo="audio", sha256=sha, dados=dados,
        evidencia=_evidencia_audio(), canal="lateral", forma_de_onda=calcular_forma_de_onda(dados, "a.wav"),
    )
    for html in (ui.item_lateral(item, ativo=True), ui.linha_evidencia(item, ativa=False)):
        assert "<script>" not in html and "&lt;script&gt;" in html
    assert "cp-item--ativo" in ui.item_lateral(item, True) and "cp-item--inativo" in ui.item_lateral(item, False)

    onda = ui.forma_de_onda(item.forma_de_onda, (1.0, 2.0))
    destacadas = onda.count("cp-onda-barra--trecho")
    assert 45 <= destacadas <= 60, destacadas  # ~1/3 de 160 barras
    assert "cp-onda-cursor" in onda and "cp-onda-cursor" not in ui.forma_de_onda(item.forma_de_onda, None)

    assert ui.markdown_seguro("R$ 300,00 e R$ 150,00") == "R\\$ 300,00 e R\\$ 150,00"
    assert ui.tempo(125.4) == "02:05"
    print("PASS: componentes escapam texto, destacam o trecho e protegem valores em R$")


def testar_relatorio() -> None:
    """O relatorio leva o hash completo de cada evidencia e o historico."""
    registro = RegistroEvidencias()
    dados = _wav()
    chave, sha = chave_do_arquivo("audio", dados)
    item = registro.registrar(chave, nome="relato.wav", tipo="audio", sha256=sha, dados=dados,
                              evidencia=_evidencia_audio(), canal="chat")
    mensagens = [
        {"papel": "user", "conteudo": "Qual a CPU?", "anexos": [{"nome": "relato.wav", "id": "E01"}], "hora": "14:09"},
        {"papel": "assistant", "conteudo": "92%, segundo o audio.", "ids_evidencias": ["E01"], "hora": "14:09"},
    ]
    texto = gerar_relatorio(datetime(2026, 10, 22, 14, 3), [item], {"E01"}, None, mensagens)
    assert sha in texto and "E01" in texto and "92%, segundo o audio." in texto
    print("PASS: relatorio com hash SHA-256 e perguntas/respostas")


if __name__ == "__main__":
    testar_registro()
    testar_forma_de_onda()
    testar_componentes()
    testar_relatorio()
