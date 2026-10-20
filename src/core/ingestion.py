"""Despachante unificado de ingestao do OmniAssistant.

Recebe qualquer EntradaUsuario (imagem, audio ou texto), roteia para o processador
especialista sob demanda (lazy loading) e devolve sempre uma EvidenciaMultimodal.
Tambem audita conflitos entre o que a imagem mostra e o que o audio relata.
"""

import argparse
import json
import re
from pathlib import Path

from src.core.contracts import EntradaUsuario, EvidenciaMultimodal

# Numero em formato pt-BR ("1.500,00", "150,00") ou simples ("150", "92.5")
_NUMERO = r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?"

# Valores de alta relevancia para auditoria; cada categoria e comparada separadamente
PADROES_RELEVANTES: dict[str, list[re.Pattern[str]]] = {
    "valor_monetario": [
        re.compile(rf"R\$\s*({_NUMERO})", re.IGNORECASE),
        re.compile(rf"\b({_NUMERO})\s*reais\b", re.IGNORECASE),
    ],
    "percentual": [
        re.compile(rf"\b({_NUMERO})\s*(?:%|por\s*cento)", re.IGNORECASE),
    ],
    "horario": [
        re.compile(r"\b(\d{1,2})\s*(?::|h)\s*(\d{2})?(?!\w)", re.IGNORECASE),
    ],
}


def despachar_ingestao(entrada: EntradaUsuario) -> EvidenciaMultimodal:
    """Roteia a entrada para o processador especialista sob demanda (Lazy Loading).

    Args:
        entrada: Entrada ja validada pelo contrato EntradaUsuario.

    Returns:
        Evidencia normalizada, pronta para o agente.

    Raises:
        ValueError: Tipo desconhecido ou midia rejeitada pelo processador.
    """
    if entrada.tipo == "texto":
        return EvidenciaMultimodal(
            origem="texto",
            resumo_informacao=entrada.texto_comando.strip(),
        )
    elif entrada.tipo == "imagem":
        # Importacao sob demanda: nao carrega Pillow/Gemini se nao precisar
        from src.vision.processor import processar_imagem

        assert entrada.caminho_arquivo is not None
        return processar_imagem(entrada.caminho_arquivo)
    elif entrada.tipo == "audio":
        # Importacao sob demanda: nao carrega Whisper na memoria se for apenas imagem/texto
        from src.audio.processor import processar_audio

        assert entrada.caminho_arquivo is not None
        return processar_audio(entrada.caminho_arquivo)
    else:
        raise ValueError(f"Tipo de entrada desconhecido: {entrada.tipo}")


def _normalizar_numero(bruto: str) -> float:
    """Converte "1.500,00", "150,00", "150" ou "92.5" em float."""
    if "," in bruto:
        return float(bruto.replace(".", "").replace(",", "."))
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", bruto):  # "1.500" = mil e quinhentos
        return float(bruto.replace(".", ""))
    return float(bruto)


def extrair_valores_relevantes(texto: str) -> dict[str, set[str]]:
    """Extrai valores monetarios, percentuais e horarios ja normalizados.

    Args:
        texto: Resumo de uma evidencia.

    Returns:
        Conjunto de valores normalizados por categoria (ex.: {"valor_monetario": {"R$ 150.00"}}).
    """
    valores: dict[str, set[str]] = {categoria: set() for categoria in PADROES_RELEVANTES}

    for padrao in PADROES_RELEVANTES["valor_monetario"]:
        for bruto in padrao.findall(texto):
            valores["valor_monetario"].add(f"R$ {_normalizar_numero(bruto):.2f}")

    for padrao in PADROES_RELEVANTES["percentual"]:
        for bruto in padrao.findall(texto):
            valores["percentual"].add(f"{_normalizar_numero(bruto):g}%")

    for padrao in PADROES_RELEVANTES["horario"]:
        for hora, minuto in padrao.findall(texto):
            h, m = int(hora), int(minuto or 0)
            if h < 24 and m < 60:
                valores["horario"].add(f"{h:02d}:{m:02d}")

    return valores


def auditar_conflito_evidencias(evidencia_visao: EvidenciaMultimodal, evidencia_audio: EvidenciaMultimodal) -> dict:
    """Verifica se ha numeros de alta relevancia divergentes entre imagem e audio.

    Ha divergencia numa categoria quando as duas fontes citam valores dela e nenhum
    valor coincide (ex.: print mostra R$ 150,00 e o audio fala R$ 200,00). Nenhuma
    fonte e descartada: o conflito e sinalizado para decisao humana.

    Args:
        evidencia_visao: Evidencia extraida do print.
        evidencia_audio: Evidencia extraida do audio.

    Returns:
        Relatorio com as duas fontes, os valores comparados e o parecer.
    """
    valores_visao = extrair_valores_relevantes(evidencia_visao.resumo_informacao)
    valores_audio = extrair_valores_relevantes(evidencia_audio.resumo_informacao)

    divergencias = []
    for categoria in PADROES_RELEVANTES:
        na_imagem, no_audio = valores_visao[categoria], valores_audio[categoria]
        if na_imagem and no_audio and not (na_imagem & no_audio):
            divergencias.append(
                f"{categoria}: imagem mostra {', '.join(sorted(na_imagem))}; "
                f"audio cita {', '.join(sorted(no_audio))}"
            )

    conflito_detectado = bool(divergencias)
    if conflito_detectado:
        motivo = (
            "DIVERGENCIA entre imagem e audio. Ambas as fontes foram mantidas; "
            "encaminhar para decisao humana antes de qualquer acao."
        )
    else:
        motivo = "Fontes consistentes ou complementares."

    return {
        "visao": evidencia_visao.resumo_informacao,
        "audio": evidencia_audio.resumo_informacao,
        "valores_comparados": {
            "visao": {c: sorted(v) for c, v in valores_visao.items() if v},
            "audio": {c: sorted(v) for c, v in valores_audio.items() if v},
        },
        "divergencias": divergencias,
        "divergencia_identificada": conflito_detectado,
        "parecer_auditoria": motivo,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Despachante Multimodal OmniAssistant")
    parser.add_argument("tipo", choices=["imagem", "audio", "texto", "conflito"])
    parser.add_argument("--caminho", type=Path, help="Arquivo para os tipos imagem e audio")
    parser.add_argument("--texto", default="", help="Comando para o tipo texto")
    parser.add_argument("--imagem", type=Path, help="Print usado no modo conflito")
    parser.add_argument("--audio", type=Path, help="Audio usado no modo conflito")
    args = parser.parse_args()

    if args.tipo == "conflito":
        if not (args.imagem and args.audio):
            parser.error("o modo conflito exige --imagem e --audio")
        evidencia_visao = despachar_ingestao(EntradaUsuario(tipo="imagem", caminho_arquivo=args.imagem))
        evidencia_audio = despachar_ingestao(EntradaUsuario(tipo="audio", caminho_arquivo=args.audio))
        relatorio = auditar_conflito_evidencias(evidencia_visao, evidencia_audio)
        print(json.dumps(relatorio, indent=2, ensure_ascii=False))
    else:
        cmd = EntradaUsuario(tipo=args.tipo, caminho_arquivo=args.caminho, texto_comando=args.texto)
        resultado = despachar_ingestao(cmd)
        print(resultado.model_dump_json(indent=2))
