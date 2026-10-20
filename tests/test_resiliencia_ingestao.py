"""Testes de resiliencia do pipeline de ingestao (sem chamadas a API).

Uso:
    python -m tests.test_resiliencia_ingestao
"""

import sys
import tempfile
import wave
from pathlib import Path

from src.core.contracts import EntradaUsuario, EvidenciaMultimodal
from src.core.ingestion import auditar_conflito_evidencias, despachar_ingestao


def testar_lazy_loading() -> None:
    """Processar texto nao deve carregar o modulo de audio (Whisper) nem o de visao."""
    entrada_txt = EntradaUsuario(tipo="texto", texto_comando="Ola Omni")
    evidencia = despachar_ingestao(entrada_txt)

    assert evidencia.origem == "texto"
    assert "src.audio.processor" not in sys.modules, "FALHA: Modulo de audio carregado indevidamente!"
    assert "src.vision.processor" not in sys.modules, "FALHA: Modulo de visao carregado indevidamente!"
    print("PASS: Lazy loading validado com sucesso. Texto puro nao consome memoria de audio.")


def testar_imagem_corrompida(pasta: Path) -> None:
    """Um .png com bytes aleatorios deve ser recusado antes de gastar rede."""
    falsa = pasta / "corrompida.png"
    falsa.write_bytes(b"isto nao e uma imagem" * 50)

    try:
        despachar_ingestao(EntradaUsuario(tipo="imagem", caminho_arquivo=falsa))
        raise AssertionError("FALHA: imagem corrompida foi aceita!")
    except ValueError as e:
        print("PASS: Imagem corrompida recusada ->", e)


def testar_audio_silencioso(pasta: Path) -> None:
    """Um WAV de 2s de silencio deve ser barrado antes de carregar o modelo Whisper."""
    try:
        import whisper  # noqa: F401
    except ImportError:
        print("SKIP: openai-whisper nao instalado; teste de audio silencioso ignorado.")
        return

    silencio = pasta / "silencio.wav"
    with wave.open(str(silencio), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16_000)
        wav.writeframes(b"\x00\x00" * 16_000 * 2)

    from src.audio.processor import carregar_modelo_whisper

    try:
        despachar_ingestao(EntradaUsuario(tipo="audio", caminho_arquivo=silencio))
        raise AssertionError("FALHA: audio silencioso foi aceito!")
    except ValueError as e:
        assert carregar_modelo_whisper.cache_info().currsize == 0, "FALHA: Whisper carregado para audio silencioso!"
        print("PASS: Audio silencioso recusado sem carregar o Whisper ->", e)


def testar_deteccao_conflito() -> None:
    """Print com R$ 150,00 e audio pedindo estorno de R$ 200,00 deve gerar divergencia."""
    visao = EvidenciaMultimodal(origem="visao", resumo_informacao="Tela do pedido 4821\nDados: Total R$ 150,00")
    audio = EvidenciaMultimodal(origem="audio", resumo_informacao="Oi, favor estornar o pedido de R$ 200,00")
    relatorio = auditar_conflito_evidencias(visao, audio)
    assert relatorio["divergencia_identificada"], "FALHA: conflito de valores nao detectado!"

    audio_ok = EvidenciaMultimodal(origem="audio", resumo_informacao="Favor estornar o pedido de 150 reais")
    assert not auditar_conflito_evidencias(visao, audio_ok)["divergencia_identificada"], (
        "FALHA: valores iguais foram marcados como conflito!"
    )
    print("PASS: Divergencia detectada ->", relatorio["divergencias"][0])


if __name__ == "__main__":
    testar_lazy_loading()  # precisa rodar primeiro, antes de qualquer import de visao/audio
    with tempfile.TemporaryDirectory() as tmp:
        testar_imagem_corrompida(Path(tmp))
        testar_audio_silencioso(Path(tmp))
    testar_deteccao_conflito()
