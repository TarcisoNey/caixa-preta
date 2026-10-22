"""Componentes visuais do design "Caixa Preta · Conversação" (Figma).

Cada funcao devolve um trecho de HTML com as classes de src/ui/tema.css. Todo texto
que vem de fora (nome de arquivo, transcricao, leitura do Gemini) passa por escape().
A mesma peca e usada em todos os lugares em que aparece, com variantes em vez de copias:
chip de evidencia, pill de status, indicador, cartao, item da barra lateral e linha de evidencia.
"""

from html import escape
from pathlib import Path

import streamlit as st

from src.ui.midia import FormaDeOnda
from src.ui.registro import ItemEvidencia

CAMINHO_ICONES = "app/static/icones"
CAMINHO_CSS = Path(__file__).with_name("tema.css")


def aplicar_tema() -> None:
    """Injeta os tokens e estilos do design na pagina (sem ocupar espaco no layout)."""
    st.html(f"<style>{CAMINHO_CSS.read_text(encoding='utf-8')}</style>")


def markdown_seguro(texto: str) -> str:
    """Escapa "$": sem isso o st.markdown le "R$ 300,00 ... R$ 150,00" como LaTeX e some com os cifroes."""
    return texto.replace("$", "\\$")


def tempo(segundos: float) -> str:
    """Formata segundos como mm:ss."""
    total = max(int(round(segundos)), 0)
    return f"{total // 60:02d}:{total % 60:02d}"


def icone(nome: str, tamanho: int) -> str:
    return (
        f'<img class="cp-icone" src="{CAMINHO_ICONES}/{nome}.svg" '
        f'width="{tamanho}" height="{tamanho}" alt="">'
    )


def eyebrow(texto: str) -> str:
    return f'<div class="cp-eyebrow">{escape(texto)}</div>'


def chip(eid: str, destaque: bool = False) -> str:
    classe = "cp-chip cp-chip--destaque" if destaque else "cp-chip"
    return f'<span class="{classe}">{escape(eid)}</span>'


def pill_status(rotulo: str, tom: str) -> str:
    """Status da investigacao. tom: "neutro" | "analise" | "alerta"."""
    return f'<span class="cp-pill cp-pill--{tom}">{escape(rotulo)}</span>'


def indicador(rotulo: str, tom: str) -> str:
    """Status de sistema (ponto + texto, sem fundo). tom: "ok" | "atencao"."""
    return f'<span class="cp-indicador cp-indicador--{tom}">{escape(rotulo)}</span>'


def logo() -> str:
    return (
        '<div class="cp-logo">'
        f'{icone("logo", 32)}'
        '<div><div class="cp-logo-nome">caixa preta</div>'
        '<div class="cp-logo-sub">OMNIAGENT DE IA</div></div>'
        "</div>"
    )


def bloco_squad(nome: str, dominio: str) -> str:
    return (
        '<div class="cp-squad">'
        f'<span class="cp-squad-avatar">{escape(nome[:1].upper())}</span>'
        f'<div><div class="cp-squad-nome">{escape(nome)}</div>'
        f'<div class="cp-squad-sub">{escape(dominio)}</div></div>'
        "</div>"
    )


def topbar(rotulo_sessao: str, status_rotulo: str, status_tom: str) -> str:
    return (
        '<div class="cp-topbar">'
        '<span class="cp-crumb">Investigação</span>'
        f'{icone("chevron-direita", 12)}'
        f'<span class="cp-crumb-id">{escape(rotulo_sessao)}</span>'
        f"{pill_status(status_rotulo, status_tom)}"
        "</div>"
    )


def cabecalho_pagina(titulo: str, itens_meta: list[str]) -> str:
    """Titulo grande + linha de metadados separados por pontos. itens_meta ja vem em HTML."""
    separador = '<span class="cp-sep"></span>'
    return (
        '<div class="cp-cabecalho">'
        f'<h1 class="cp-titulo">{escape(titulo)}</h1>'
        f'<div class="cp-meta">{separador.join(itens_meta)}</div>'
        "</div>"
    )


def cabecalho_cartao(nome_icone: str, titulo: str, marcador: str = "", direita: str = "") -> str:
    """Topo de cartao: icone, titulo, marcador (chip ou badge) e texto alinhado a direita."""
    return (
        '<div class="cp-cartao-topo">'
        f"{icone(nome_icone, 15)}"
        f'<span class="cp-cartao-titulo">{escape(titulo)}</span>'
        f"{marcador}"
        '<span class="cp-espaco"></span>'
        f'<span class="cp-cartao-direita">{direita}</span>'
        "</div>"
    )


def badge(texto: str) -> str:
    return f'<span class="cp-badge">{escape(texto)}</span>'


def rodape_cartao(esquerda: str, direita: str = "") -> str:
    return f'<div class="cp-cartao-rodape"><span>{esquerda}</span><span>{direita}</span></div>'


def callout(rotulo: str, direita: str, texto: str, tom: str = "destaque") -> str:
    """Bloco com borda lateral (hipotese, divergencia). tom: "destaque" | "alerta"."""
    return (
        f'<div class="cp-callout cp-callout--{tom}">'
        f'<div class="cp-callout-topo"><span class="cp-callout-rotulo">{escape(rotulo)}</span>'
        f"<span>{escape(direita)}</span></div>"
        f"<p>{escape(texto)}</p>"
        "</div>"
    )


def forma_de_onda(onda: FormaDeOnda, trecho: tuple[float, float] | None) -> str:
    """Forma de onda em barras ocupando toda a largura. O trecho vinculado fica destacado em ambar.

    Barras em <span> (e nao SVG) porque o st.html sanitiza SVG.
    """
    duracao = max(onda.duracao_segundos, 0.001)
    ini, fim = trecho if trecho else (-1.0, -1.0)

    partes = []
    if trecho:
        esquerda = ini / duracao * 100
        largura = max(min(fim / duracao, 1.0) * 100 - esquerda, 0.4)
        partes.append(f'<span class="cp-onda-trecho" style="left:{esquerda:.2f}%;width:{largura:.2f}%"></span>')
    for i, pico in enumerate(onda.picos):
        meio = (i + 0.5) / len(onda.picos) * duracao
        classe = "cp-onda-barra cp-onda-barra--trecho" if ini <= meio <= fim else "cp-onda-barra"
        partes.append(f'<span class="{classe}" style="height:{max(pico * 84, 7):.0f}%"></span>')
    if trecho:
        partes.append(f'<span class="cp-onda-cursor" style="left:{ini / duracao * 100:.2f}%"></span>')
    return (
        '<div class="cp-onda" role="img" aria-label="Forma de onda do áudio">'
        f'<div class="cp-onda-barras">{"".join(partes)}</div></div>'
    )


def _detalhe_item(item: ItemEvidencia) -> str:
    if item.tipo == "imagem":
        return f"Gemini · confiança {item.evidencia.confianca_declarada:.0%}"
    partes = ["Whisper"]
    if item.forma_de_onda:
        partes.append(tempo(item.forma_de_onda.duracao_segundos))
    if item.evidencia.segmentos_audio:
        partes.append(f"{len(item.evidencia.segmentos_audio)} trechos")
    return " · ".join(partes)


def item_lateral(item: ItemEvidencia, ativo: bool) -> str:
    """Item da lista da barra lateral. Mesma estrutura nas duas variantes (ativo / fora da pergunta)."""
    variante = "cp-item--ativo" if ativo else "cp-item--inativo"
    return (
        f'<div class="cp-item {variante}">'
        f'<div class="cp-item-topo">{chip(item.id, destaque=ativo)}'
        f'<span class="cp-item-tipo">{escape(item.rotulo_tipo.upper())}</span></div>'
        f'<div class="cp-item-nome">{escape(item.nome)}</div>'
        f'<div class="cp-item-meta">{escape(_detalhe_item(item))}</div>'
        "</div>"
    )


def linha_evidencia(item: ItemEvidencia, ativa: bool) -> str:
    """Linha do acordeao de evidencias: chip, nome, origem e hash do arquivo."""
    variante = "" if ativa else " cp-linha--inativa"
    origem = "barra lateral" if item.canal == "lateral" else "chat"
    return (
        f'<div class="cp-linha{variante}">'
        f"{chip(item.id, destaque=ativa)}"
        f'{icone("imagem" if item.tipo == "imagem" else "audio", 13)}'
        f'<div class="cp-linha-texto"><div class="cp-linha-nome">{escape(item.nome)}</div>'
        f'<div class="cp-linha-meta">{escape(_detalhe_item(item))} · enviado pelo {origem} · '
        f'{item.recebida_em:%H:%M:%S}</div></div>'
        f'<span class="cp-linha-hash" title="SHA-256 {item.sha256}">{item.hash_curto}</span>'
        "</div>"
    )


def pergunta(texto: str, hora: str) -> str:
    corpo = f'<p class="cp-pergunta-texto">{escape(texto)}</p>' if texto else ""
    return f'<div class="cp-pergunta">{eyebrow(f"PERGUNTA · {hora}")}{corpo}</div>'


def linha_contexto(ids: list[str]) -> str:
    alvo = f"{len(ids)} EVIDÊNCIA{'S' if len(ids) != 1 else ''}" + (f" · {' '.join(ids)}" if ids else "")
    return (
        '<div class="cp-contexto">'
        f"<span>CONTEXTO: {escape(alvo)}</span>"
        "<span>Respostas citam a fonte de cada dado</span>"
        "</div>"
    )
