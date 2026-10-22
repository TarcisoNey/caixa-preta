"""Orquestrador agentico do OmniAssistant (Percepcao -> Raciocinio -> Acao -> Resposta).

Recebe as evidencias multimodais, deixa o Gemini decidir quais ferramentas locais
chamar e executa cada chamada por um despachante com allowlist e schemas estritos.
"""

import json
from time import perf_counter
from typing import Callable

from google.genai import types
from pydantic import BaseModel, ConfigDict, Field

from src.core.config import MODEL, criar_cliente_gemini
from src.core.contracts import EvidenciaMultimodal
from src.tools.local import calcular_total, consultar_item, validar_codigo

# validar -> consultar -> calcular -> resposta ja usa 4 turnos; folga para perguntas com mais de um item
MAX_TURNOS = 6


# Contratos estritos dos argumentos das ferramentas
class CodigoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    codigo: str = Field(description="Codigo do recurso no catalogo (ex: A101, F606)")


class TotalArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    quantidade: float = Field(ge=0.1, le=1000.0, description="Quantidade de itens, meses ou horas")
    preco_unitario: float = Field(ge=0.01, le=100000.0, description="Preco unitario em BRL")


REGISTRO_TOOLS: dict[str, tuple[Callable[..., dict], type[BaseModel], str]] = {
    "consultar_item": (
        consultar_item,
        CodigoArgs,
        "Consulta nome, preco (BRL) e setor de um recurso de infraestrutura por codigo no banco SQLite.",
    ),
    "calcular_total": (
        calcular_total,
        TotalArgs,
        "Calcula o valor total em BRL a partir de quantidade e preco unitario.",
    ),
    "validar_codigo": (
        validar_codigo,
        CodigoArgs,
        "Valida o formato de um codigo de recurso (1 letra maiuscula + 3 digitos).",
    ),
}

FERRAMENTAS_GEMINI = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name=nome,
        description=desc,
        parameters_json_schema=schema.model_json_schema(),
    )
    for nome, (_, schema, desc) in REGISTRO_TOOLS.items()
])

SYSTEM_INSTRUCTION = (
    "Voce e o orquestrador do OmniAssistant da Squad Caixa-Preta, um assistente de Auditoria de "
    "Infraestrutura e TI. Voce recebe evidencias extraidas de prints de consoles cloud/monitoramento "
    "(origem 'visao'), de audios de incidentes transcritos pelo Whisper (origem 'audio') e de texto. "
    "Quando precisar de precos ou dados cadastrais de recursos, acione consultar_item. "
    "Para qualquer conta, acione calcular_total. Nunca chute valores nem faca contas de cabeca. "
    "Se o campo auditoria_conflito indicar divergencia entre imagem e audio, NAO escolha um lado: "
    "apresente os dois valores e recomende validacao humana. "
    "Na resposta final, em portugues, cite de onde veio cada informacao "
    "(ex.: 'conforme o print', 'segundo o audio', 'conforme o catalogo')."
)


def despachar_tool(chamada: types.FunctionCall) -> dict:
    """Executa uma chamada de ferramenta do modelo, so se estiver na allowlist e com argumentos validos."""
    nome = chamada.name or ""
    if nome not in REGISTRO_TOOLS:
        return {"erro": f"Ferramenta '{nome}' nao autorizada."}

    funcao, schema, _ = REGISTRO_TOOLS[nome]
    try:
        args = schema.model_validate(chamada.args or {}).model_dump()
        return funcao(**args)
    except Exception as e:
        return {"erro": f"Argumentos invalidos para {nome}: {type(e).__name__}"}


def _montar_payload(pergunta: str, evidencias: list[EvidenciaMultimodal]) -> str:
    """Serializa pergunta + evidencias e, se houver imagem e audio, anexa a auditoria de conflito."""
    payload: dict = {
        "pergunta": pergunta,
        "evidencias_multimodais": [e.model_dump() for e in evidencias],
    }
    visao = next((e for e in evidencias if e.origem == "visao"), None)
    audio = next((e for e in evidencias if e.origem == "audio"), None)
    if visao and audio:
        from src.core.ingestion import auditar_conflito_evidencias

        auditoria = auditar_conflito_evidencias(visao, audio)
        payload["auditoria_conflito"] = {
            "divergencia_identificada": auditoria["divergencia_identificada"],
            "divergencias": auditoria["divergencias"],
            "parecer_auditoria": auditoria["parecer_auditoria"],
        }
    return json.dumps(payload, ensure_ascii=False)


def executar_agente(pergunta: str, evidencias: list[EvidenciaMultimodal]) -> dict:
    """Executa o loop agentico multimodal em multiplos turnos com limite de passos.

    Args:
        pergunta: Pergunta ou comando do usuario.
        evidencias: Evidencias ja normalizadas pela ingestao.

    Returns:
        Resposta final, rastro das ferramentas e telemetria (turnos, tokens, tempo).
    """
    inicio = perf_counter()
    trace_ferramentas = []

    historico = [types.Content(role="user", parts=[types.Part.from_text(text=_montar_payload(pergunta, evidencias))])]

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_INSTRUCTION,
        temperature=0.0,
        tools=[FERRAMENTAS_GEMINI],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    resposta_final = "Limite de chamadas atingido sem resposta conclusiva."
    tokens_usados = 0
    turnos_executados = 0
    cliente = criar_cliente_gemini()

    # Loop com trava de seguranca (max MAX_TURNOS turnos)
    for _ in range(MAX_TURNOS):
        turnos_executados += 1
        resposta = cliente.models.generate_content(model=MODEL, contents=historico, config=config)
        if resposta.usage_metadata and resposta.usage_metadata.total_token_count:
            tokens_usados += resposta.usage_metadata.total_token_count

        candidato = resposta.candidates[0].content if resposta.candidates else None
        if not candidato:
            resposta_final = "Sem resposta do modelo."
            break

        historico.append(candidato)
        chamadas = [p.function_call for p in candidato.parts or [] if p.function_call is not None]

        # Se o modelo nao pediu mais ferramentas, ele concluiu a resposta!
        if not chamadas:
            texto = "".join(p.text for p in candidato.parts or [] if p.text and not p.thought)
            resposta_final = texto.strip() or "Resposta conclusiva emitida."
            break

        # Executa cada ferramenta solicitada e devolve a observacao ao modelo
        partes_resposta = []
        for call in chamadas:
            t0 = perf_counter()
            resultado = despachar_tool(call)
            duracao_ms = round((perf_counter() - t0) * 1000, 1)

            trace_ferramentas.append({
                "ferramenta": call.name,
                "argumentos": dict(call.args or {}),
                "resultado": resultado,
                "duracao_ms": duracao_ms,
            })
            partes_resposta.append(types.Part.from_function_response(name=call.name or "", response=resultado))

        # Respostas de funcao voltam no papel "user", como espera a API do Gemini
        historico.append(types.Content(role="user", parts=partes_resposta))

    return {
        "resposta": resposta_final,
        "rastro_ferramentas": trace_ferramentas,
        "total_turnos": turnos_executados,
        "tokens_estimados": tokens_usados,
        "tempo_total_ms": round((perf_counter() - inicio) * 1000, 1),
    }


if __name__ == "__main__":
    evidencia_teste = [
        EvidenciaMultimodal(origem="visao", resumo_informacao="Print do inventario do datacenter mostrando o item A101"),
        EvidenciaMultimodal(origem="audio", resumo_informacao="Plantonista pede a compra de 4 unidades deste item para o rack 3"),
    ]
    resultado = executar_agente("Qual o custo total desta solicitacao?", evidencia_teste)
    print(json.dumps(resultado, indent=2, ensure_ascii=False))
