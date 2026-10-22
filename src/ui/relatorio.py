"""Relatorio da investigacao (botao "Relatorio" da topbar), em Markdown."""

from datetime import datetime

from src.ui.componentes import tempo
from src.ui.registro import ItemEvidencia


def gerar_relatorio(
    inicio: datetime,
    itens: list[ItemEvidencia],
    ids_ativos: set[str],
    auditoria: dict | None,
    mensagens: list[dict],
) -> str:
    """Monta o relatorio com evidencias (e hash), auditoria de conflito e perguntas/respostas."""
    linhas = [
        "# Relatório de investigação · Caixa-Preta",
        "",
        f"- Sessão iniciada em {inicio:%d/%m/%Y %H:%M}",
        f"- Relatório gerado em {datetime.now():%d/%m/%Y %H:%M}",
        f"- Evidências: {len(itens)} na sessão, {len(ids_ativos)} ativas",
        "",
        "## Evidências",
        "",
    ]
    if not itens:
        linhas.append("Nenhuma evidência enviada.")
    for item in itens:
        situacao = "ativa" if item.id in ids_ativos else "fora da última pergunta"
        linhas += [
            f"### {item.id} · {item.rotulo_tipo} · {item.nome}",
            "",
            f"- SHA-256: `{item.sha256}`",
            f"- Recebida às {item.recebida_em:%H:%M:%S} pelo {'chat' if item.canal == 'chat' else 'painel lateral'} ({situacao})",
            f"- Confiança declarada: {item.evidencia.confianca_declarada:.0%}",
            "",
            item.evidencia.resumo_informacao,
            "",
        ]
        for seg in item.evidencia.segmentos_audio:
            linhas.append(f"- `{tempo(seg.inicio_segundos)}–{tempo(seg.fim_segundos)}` {seg.texto_transcrito}")
        if item.evidencia.segmentos_audio:
            linhas.append("")

    if auditoria:
        linhas += ["## Auditoria de conflito (imagem × áudio)", "", auditoria["parecer_auditoria"], ""]
        linhas += [f"- {d}" for d in auditoria["divergencias"]]
        linhas.append("")

    linhas += ["## Perguntas e respostas", ""]
    if not mensagens:
        linhas.append("Nenhuma pergunta feita.")
    for msg in mensagens:
        if msg["papel"] == "user":
            anexos = ", ".join(a.get("id") or a["nome"] for a in msg.get("anexos", []))
            linhas += [f"**Pergunta ({msg.get('hora', '--:--')}):** {msg['conteudo'] or '(só anexos)'}", ""]
            if anexos:
                linhas += [f"Anexos: {anexos}", ""]
            continue
        linhas += [f"**Resposta ({msg.get('hora', '--:--')}):**", "", msg["conteudo"], ""]
        if msg.get("ids_evidencias"):
            linhas += [f"Evidências consideradas: {', '.join(msg['ids_evidencias'])}", ""]
        for idx, tool in enumerate((msg.get("telemetria") or {}).get("rastro_ferramentas", []), start=1):
            linhas.append(f"{idx}. `{tool['ferramenta']}` {tool['argumentos']} → {tool['resultado']}")
        linhas.append("")
    return "\n".join(linhas)
