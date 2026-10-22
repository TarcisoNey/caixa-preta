"""Forma de onda dos audios para o player da interface.

Le o audio com o modulo wave (WAV, como as gravacoes do microfone) ou com o ffmpeg
(MP3, OGG, M4A; o mesmo que o Whisper ja exige). Se nao der para decodificar, a UI
mostra so o player, sem a forma de onda.
"""

import subprocess
import wave
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

TAXA_AMOSTRAGEM = 16_000


@dataclass(frozen=True)
class FormaDeOnda:
    picos: tuple[float, ...]  # altura de cada barra, de 0.0 a 1.0
    duracao_segundos: float


def _amostras_wav(dados: bytes) -> tuple[np.ndarray, int] | None:
    try:
        with wave.open(BytesIO(dados)) as arquivo:
            if arquivo.getsampwidth() != 2:
                return None
            canais, taxa = arquivo.getnchannels(), arquivo.getframerate()
            bruto = np.frombuffer(arquivo.readframes(arquivo.getnframes()), dtype=np.int16)
    except (wave.Error, EOFError):
        return None
    if canais > 1:
        bruto = bruto[: len(bruto) - len(bruto) % canais].reshape(-1, canais).mean(axis=1)
    return bruto.astype(np.float32) / 32768.0, taxa


def _amostras_ffmpeg(dados: bytes, nome: str) -> tuple[np.ndarray, int] | None:
    # Arquivo temporario em vez de pipe: M4A guarda o indice no fim e nao e lido de stdin
    with TemporaryDirectory() as tmp:
        caminho = Path(tmp) / (Path(nome).name or "audio")
        caminho.write_bytes(dados)
        comando = [
            "ffmpeg", "-nostdin", "-v", "error", "-i", str(caminho),
            "-f", "s16le", "-ac", "1", "-ar", str(TAXA_AMOSTRAGEM), "-",
        ]
        try:
            saida = subprocess.run(comando, capture_output=True, timeout=30, check=True).stdout
        except (FileNotFoundError, subprocess.SubprocessError):
            return None
    return np.frombuffer(saida, dtype=np.int16).astype(np.float32) / 32768.0, TAXA_AMOSTRAGEM


def calcular_forma_de_onda(dados: bytes, nome: str, barras: int = 160) -> FormaDeOnda | None:
    """Reduz o audio a `barras` picos normalizados, para desenhar a forma de onda."""
    lido = _amostras_wav(dados) if nome.lower().endswith(".wav") else None
    lido = lido or _amostras_ffmpeg(dados, nome)
    if lido is None:
        return None
    amostras, taxa = lido
    if amostras.size < barras:
        return None

    picos = np.array([np.abs(bloco).max() for bloco in np.array_split(amostras, barras)])
    maior = float(picos.max())
    if maior <= 0:
        return None
    # Piso de 8% para o silencio ainda aparecer como barra
    normalizados = np.clip(picos / maior, 0.08, 1.0)
    return FormaDeOnda(
        picos=tuple(round(float(p), 3) for p in normalizados),
        duracao_segundos=amostras.size / taxa,
    )
