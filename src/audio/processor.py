import sys
from functools import lru_cache
from pathlib import Path
import numpy as np
import whisper
from whisper.model import Whisper
from src.core.config import WHISPER_MODEL
from src.core.contracts import EvidenciaMultimodal, SegmentoFala

EXTENSOES_SUPORTADAS = {".wav", ".mp3", ".ogg", ".m4a"}

# Vocabulario do dominio para o Whisper reconhecer melhor termos tecnicos dos relatos de incidente
CONTEXTO_DOMINIO = (
    "Relato de incidente de infraestrutura de TI: servidor, cluster, pod, Kubernetes, deploy, "
    "AWS, GCP, Azure, bucket S3, EC2, security group, firewall, CPU, memoria, latencia, alarme, "
    "plantao, rollback, producao, homologacao."
)

@lru_cache(maxsize=1)
def carregar_modelo_whisper() -> Whisper:
    print(f"Iniciando instancia do Whisper {WHISPER_MODEL} na CPU...")
    return whisper.load_model(WHISPER_MODEL, device="cpu")

def processar_audio(caminho: Path) -> EvidenciaMultimodal:
    """Valida o audio localmente e extrai a transcricao com segmentos temporais."""
    if not caminho.is_file() or caminho.stat().st_size > 10_000_000:
        raise ValueError("O audio deve existir no disco e ter ate 10 MB.")

    if caminho.suffix.lower() not in EXTENSOES_SUPORTADAS:
        raise ValueError("Extensao de audio nao suportada. Use WAV, MP3, OGG ou M4A.")

    try:
        amostras = whisper.load_audio(str(caminho))
    except (RuntimeError, FileNotFoundError) as e:
        raise ValueError(
            "Nao foi possivel decodificar o audio. Verifique se o arquivo nao esta corrompido "
            "e se o ffmpeg esta instalado (macOS: brew install ffmpeg)."
        ) from e
    duracao_seg = len(amostras) / whisper.audio.SAMPLE_RATE

    if not 0.5 <= duracao_seg <= 60.0:
        raise ValueError(f"O audio deve ter entre 0.5 e 60 segundos (recebido: {duracao_seg:.1f}s).")

    # Validacao de energia para barrar silencio absoluto
    energia_rms = float(np.sqrt(np.mean(amostras ** 2)))
    if energia_rms < 0.001:
        raise ValueError("Audio silencioso ou microfone desconectado.")

    modelo = carregar_modelo_whisper()
    resultado = modelo.transcribe(
        amostras, language="pt", fp16=False, verbose=False, initial_prompt=CONTEXTO_DOMINIO
    )

    texto_transcrito = str(resultado["text"]).strip()
    if not texto_transcrito:
        raise ValueError("Nenhuma fala compreensivel foi detectada no audio.")

    # Segmentos sem texto quebrariam o contrato SegmentoFala (texto_transcrito nao vazio)
    segmentos = [
        SegmentoFala(
            inicio_segundos=round(float(s["start"]), 2),
            fim_segundos=round(float(s["end"]), 2),
            texto_transcrito=str(s["text"]).strip()
        )
        for s in resultado["segments"]
        if str(s["text"]).strip()
    ]

    return EvidenciaMultimodal(
        origem="audio",
        resumo_informacao=texto_transcrito,
        segmentos_audio=segmentos,
        confianca_declarada=0.9
    )

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python -m src.audio.processor data/audios/relato.wav")
        sys.exit(1)
    evidencia = processar_audio(Path(sys.argv[1]))
    print(evidencia.model_dump_json(indent=2))
