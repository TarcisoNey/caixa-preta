"""Contratos de dados compartilhados do OmniAssistant.

Todos os modulos (vision, audio, tools, app) conversam APENAS atraves destas
classes. Fluxo: EntradaUsuario -> EvidenciaMultimodal -> (Acao, nos proximos dias).
"""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

try:  # Python 3.11+
    from typing import Self
except ImportError:  # Python 3.10 ou anterior
    from typing_extensions import Self


class ContratoBase(BaseModel):
    """Base de todos os contratos: rejeita campos nao declarados (extra="forbid")."""

    model_config = ConfigDict(extra="forbid")


class EntradaUsuario(ContratoBase):
    """O que o usuario enviou ao assistente.

    Attributes:
        tipo: Modalidade da entrada ("imagem", "audio" ou "texto").
        caminho_arquivo: Caminho do print/foto ou do audio. Obrigatorio para imagem e audio.
        texto_comando: Comando em texto. Obrigatorio (nao vazio) para tipo "texto".
    """

    tipo: Literal["imagem", "audio", "texto"]
    caminho_arquivo: Path | None = None
    texto_comando: str = ""

    @model_validator(mode="after")
    def validar_consistencia(self) -> Self:
        """Garante que cada tipo de entrada traz o conteudo de que precisa.

        Returns:
            A propria instancia, se for consistente.

        Raises:
            ValueError: Texto vazio, ou arquivo inexistente para imagem/audio.
        """
        if self.tipo == "texto" and not self.texto_comando.strip():
            raise ValueError("Entrada do tipo texto nao pode estar vazia.")
        if self.tipo in ("imagem", "audio"):
            if self.caminho_arquivo is None or not self.caminho_arquivo.is_file():
                raise ValueError(f"Arquivo obrigatorio nao encontrado para entrada do tipo {self.tipo}.")
        return self


class SegmentoFala(ContratoBase):
    """Trecho transcrito de um audio, com marcacao de tempo.

    Attributes:
        inicio_segundos: Inicio do trecho, em segundos (>= 0).
        fim_segundos: Fim do trecho, em segundos (>= inicio).
        texto_transcrito: Texto falado no trecho (nao vazio).
    """

    inicio_segundos: float = Field(ge=0.0)
    fim_segundos: float = Field(ge=0.0)
    texto_transcrito: str = Field(min_length=1)

    @model_validator(mode="after")
    def validar_ordem_cronologica(self) -> Self:
        """Impede segmentos que terminam antes de comecar.

        Returns:
            A propria instancia, se a ordem for valida.

        Raises:
            ValueError: Se fim_segundos < inicio_segundos.
        """
        if self.fim_segundos < self.inicio_segundos:
            raise ValueError("O timestamp final nao pode ser menor que o timestamp inicial.")
        return self


class EvidenciaMultimodal(ContratoBase):
    """Informacao extraida de uma entrada, pronta para o agente usar.

    Attributes:
        origem: De onde veio ("visao", "audio", "texto" ou "banco_dados").
        resumo_informacao: Resumo do que foi encontrado (nao vazio).
        segmentos_audio: Trechos com timestamp, quando a origem e audio.
        confianca_declarada: Confianca de 0.0 a 1.0 (padrao 1.0).
    """

    origem: Literal["visao", "audio", "texto", "banco_dados"]
    resumo_informacao: str = Field(min_length=1)
    segmentos_audio: list[SegmentoFala] = Field(default_factory=list)
    confianca_declarada: float = Field(default=1.0, ge=0.0, le=1.0)


if __name__ == "__main__":
    from pydantic import ValidationError

    entrada_valida = EntradaUsuario(
        tipo="texto",
        texto_comando="Auditar alarme de CPU do cluster de producao",
    )
    print("Contrato EntradaUsuario validado:")
    print(entrada_valida.model_dump_json(indent=2))

    print("\nTeste negativo: segmento com fim < inicio")
    try:
        SegmentoFala(inicio_segundos=5.0, fim_segundos=2.0, texto_transcrito="servidor caiu")
        print("FALHA: o segmento invalido foi aceito!")
    except ValidationError as erro:
        print("PASS: ValidationError levantado ->", erro.errors()[0]["msg"])
