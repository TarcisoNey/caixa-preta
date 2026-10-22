"""Interface web do OmniAssistant (Squad Caixa-Preta).

Layout e tokens do design "Caixa Preta · Conversação" (Figma); componentes em src/ui.

Uso:
    streamlit run app.py
"""

from datetime import datetime
from html import escape
from pathlib import Path
from tempfile import TemporaryDirectory

import streamlit as st

from src.core.agent import executar_agente
from src.core.config import MODEL, WHISPER_MODEL, chave_configurada
from src.core.contracts import EntradaUsuario
from src.core.ingestion import auditar_conflito_evidencias, despachar_ingestao
from src.tools.local import inicializar_banco
from src.ui import componentes as ui
from src.ui.midia import calcular_forma_de_onda
from src.ui.registro import ItemEvidencia, RegistroEvidencias, chave_do_arquivo
from src.ui.relatorio import gerar_relatorio

EXTENSOES_IMAGEM = ["png", "jpg", "jpeg"]
EXTENSOES_AUDIO = ["wav", "mp3", "ogg", "m4a"]
MIME_AUDIO = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".m4a": "audio/mp4"}
PERGUNTA_PADRAO = "Analise as evidencias enviadas e responda ao que foi pedido nelas."
TRECHOS_VISIVEIS = 4
MESES = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"]

# Configuracao da Pagina
st.set_page_config(
    page_title="Caixa Preta | OmniAssistant",
    page_icon="static/icones/logo.svg",
    layout="wide",
    initial_sidebar_state="expanded",
)
ui.aplicar_tema()

# Inicializa o banco SQLite local
inicializar_banco()

# Inicializacao do Estado da Sessao (Session State)
st.session_state.setdefault("historico_mensagens", [])
st.session_state.setdefault("evidencias_ativas", [])
# Registro de evidencias (IDs E01.., hash, bytes) e cache por hash: evita rodar Whisper/Gemini de novo
st.session_state.setdefault("registro", RegistroEvidencias())
# Evidencias que chegaram pelo campo do chat (arrastadas, anexadas ou gravadas) ficam valendo
# para as proximas perguntas, ate o usuario limpar a sessao
st.session_state.setdefault("itens_chat", [])
st.session_state.setdefault("ultima_pergunta_falhou", None)
# Trocar a chave dos uploaders e o jeito de limpa-los no Streamlit
st.session_state.setdefault("chave_uploader", 0)
# Trecho da transcricao selecionado em cada cartao de audio (sincroniza player e forma de onda)
st.session_state.setdefault("trechos", {})
st.session_state.setdefault("inicio_sessao", datetime.now())

registro: RegistroEvidencias = st.session_state["registro"]


def tipo_do_arquivo(arquivo) -> str | None:
    """Descobre se o arquivo e imagem ou audio pela extensao (ou pelo MIME, no caso de gravacoes)."""
    extensao = Path(arquivo.name).suffix.lower().lstrip(".")
    if extensao in EXTENSOES_IMAGEM or (arquivo.type or "").startswith("image/"):
        return "imagem"
    if extensao in EXTENSOES_AUDIO or (arquivo.type or "").startswith("audio/"):
        return "audio"
    return None


def processar_upload(arquivo, tipo: str, nome_exibido: str, canal: str) -> tuple[ItemEvidencia | None, str | None]:
    """Ingere um upload e registra a evidencia (com cache por conteudo).

    Returns:
        (item, None) em caso de sucesso, ou (None, mensagem amigavel de erro).
    """
    dados = arquivo.getvalue()
    chave, sha256 = chave_do_arquivo(tipo, dados)
    existente = registro.buscar(chave)
    if existente:
        return existente, None

    # Gravacoes do microfone podem vir sem extensao reconhecida pelo processador
    nome = Path(arquivo.name).name
    if tipo == "audio" and Path(nome).suffix.lower().lstrip(".") not in EXTENSOES_AUDIO:
        nome = f"{Path(nome).stem or 'gravacao'}.wav"

    rotulo = "Analisando print com o Gemini..." if tipo == "imagem" else "Transcrevendo audio com o Whisper..."
    with st.spinner(rotulo), TemporaryDirectory() as tmp_dir:
        caminho_tmp = Path(tmp_dir) / nome
        caminho_tmp.write_bytes(dados)
        try:
            evidencia = despachar_ingestao(EntradaUsuario(tipo=tipo, caminho_arquivo=caminho_tmp))
        except ValueError as e:
            # Problema no arquivo enviado: aviso amigavel para o usuario corrigir
            return None, f"Nao foi possivel usar {arquivo.name}: {e}"
        except Exception as e:
            return None, f"Falha ao processar {arquivo.name} ({type(e).__name__}). Verifique a conexao e tente de novo."

    item = registro.registrar(
        chave,
        nome=nome_exibido if nome_exibido != arquivo.name else nome,
        tipo=tipo,
        sha256=sha256,
        dados=dados,
        evidencia=evidencia,
        canal=canal,
        forma_de_onda=calcular_forma_de_onda(dados, nome) if tipo == "audio" else None,
    )
    return item, None


def responder(pergunta: str) -> None:
    """Roda o agente e guarda a resposta (ou a falha, para permitir retry) no historico."""
    ids = [i.id for i in st.session_state["itens_ativos"]]
    with st.spinner("OmniAssistant raciocinando e consultando ferramentas..."):
        try:
            resultado = executar_agente(pergunta, st.session_state["evidencias_ativas"])
            st.session_state["historico_mensagens"].append({
                "papel": "assistant",
                "conteudo": resultado["resposta"],
                "telemetria": resultado,
                "ids_evidencias": ids,
                "hora": f"{datetime.now():%H:%M}",
            })
            st.session_state["ultima_pergunta_falhou"] = None
        except Exception as e:
            st.session_state["historico_mensagens"].append({
                "papel": "assistant",
                "conteudo": f"Falha na execucao: {type(e).__name__} - {e}",
                "erro": True,
                "hora": f"{datetime.now():%H:%M}",
            })
            st.session_state["ultima_pergunta_falhou"] = pergunta


def selecionar_trecho(chave: str, indice: int) -> None:
    st.session_state["trechos"][chave] = indice


def limpar_sessao() -> None:
    st.session_state["historico_mensagens"].clear()
    st.session_state["evidencias_ativas"].clear()
    st.session_state["itens_chat"].clear()
    st.session_state["trechos"].clear()
    registro.limpar()
    st.session_state["ultima_pergunta_falhou"] = None
    st.session_state["chave_uploader"] += 1
    st.session_state["inicio_sessao"] = datetime.now()


# ---------- Componentes compostos (usados em mais de um lugar) ----------

def cartao_audio(item: ItemEvidencia, contexto: str) -> None:
    segmentos = item.evidencia.segmentos_audio
    chave_trecho = f"{contexto}-{item.id}"
    indice = st.session_state["trechos"].get(chave_trecho, 0) if segmentos else None
    trecho = (segmentos[indice].inicio_segundos, segmentos[indice].fim_segundos) if indice is not None else None

    if segmentos:
        direita = f'{ui.icone("vinculo", 10)}<span class="cp-cartao-direita--destaque">Trechos sincronizados com o player</span>'
    else:
        direita = "Transcrição Whisper"
    st.html(ui.cabecalho_cartao("audio", "Áudio do incidente", ui.chip(item.id, destaque=True), direita))

    detalhes = [item.nome, item.tamanho_legivel]
    if item.forma_de_onda:
        detalhes.append(ui.tempo(item.forma_de_onda.duracao_segundos))
    detalhes.append(f"sha256 {item.hash_curto}")
    st.html(f'<div class="cp-arquivo">{escape(" · ".join(detalhes))}</div>')

    if item.forma_de_onda:
        st.html(ui.forma_de_onda(item.forma_de_onda, trecho))
    st.audio(
        item.dados,
        format=MIME_AUDIO.get(Path(item.nome).suffix.lower(), "audio/wav"),
        start_time=int(trecho[0]) if trecho else 0,
    )

    def botao_trecho(i: int) -> None:
        seg = segmentos[i]
        ativo = "-ativo" if i == indice else ""
        st.button(
            f"`{ui.tempo(seg.inicio_segundos)}` {seg.texto_transcrito}",
            key=f"trecho-{contexto}-{item.id}-{i}{ativo}",
            type="tertiary",
            width="stretch",
            on_click=selecionar_trecho,
            args=(chave_trecho, i),
        )

    if segmentos:
        for i in range(min(len(segmentos), TRECHOS_VISIVEIS)):
            botao_trecho(i)
        if len(segmentos) > TRECHOS_VISIVEIS:
            with st.expander(f"Ver transcrição completa · {len(segmentos)} trechos"):
                for i in range(TRECHOS_VISIVEIS, len(segmentos)):
                    botao_trecho(i)
    else:
        st.html(f'<p class="cp-leitura">{escape(item.evidencia.resumo_informacao)}</p>')

    st.html(ui.rodape_cartao(
        '<span class="cp-rodape-mono">PT-BR · TRANSCRIÇÃO AUTOMÁTICA · WHISPER</span>',
        f'<span class="cp-rodape-mono">confiança {item.evidencia.confianca_declarada:.0%}</span>',
    ))


def cartao_imagem(item: ItemEvidencia) -> None:
    st.html(ui.cabecalho_cartao("imagem", "Print do console", ui.chip(item.id, destaque=True), "Leitura do Gemini"))
    st.html(f'<div class="cp-arquivo">{escape(f"{item.nome} · {item.tamanho_legivel} · sha256 {item.hash_curto}")}</div>')
    col_imagem, col_leitura = st.columns([2, 3], gap="medium")
    col_imagem.image(item.dados, width="stretch")
    col_leitura.html(f'<p class="cp-leitura">{escape(item.evidencia.resumo_informacao)}</p>')
    st.html(ui.rodape_cartao(
        '<span class="cp-rodape-mono">LEITURA AUTOMÁTICA · GEMINI</span>',
        f'<span class="cp-rodape-mono">confiança {item.evidencia.confianca_declarada:.0%}</span>',
    ))


def cartao_evidencia(item: ItemEvidencia, contexto: str) -> None:
    """Mesmo cartao para evidencias da barra lateral e anexos do chat."""
    with st.container(key=f"cartao-{contexto}-{item.id}", gap="small"):
        if item.tipo == "audio":
            cartao_audio(item, contexto)
        else:
            cartao_imagem(item)


def formatar_telemetria(telemetria: dict) -> str:
    segundos = f"{telemetria.get('tempo_total_ms', 0) / 1000:.1f}".replace(".", ",")
    tokens = telemetria.get("tokens_estimados")
    tokens = f"{tokens:,}".replace(",", ".") if isinstance(tokens, int) else "N/A"
    return f"{segundos} s · {telemetria.get('total_turnos', 1)} turnos · {tokens} tokens"


def cartao_resposta(msg: dict, indice: int) -> None:
    with st.container(key=f"cartao-resposta-{indice}", gap="small"):
        if msg.get("erro"):
            st.html(ui.cabecalho_cartao("info", "Falha na resposta", direita=msg.get("hora", "")))
            st.html(ui.callout("FALHA NA EXECUÇÃO", "Use “Tentar novamente” abaixo", msg["conteudo"], tom="alerta"))
            st.html(ui.rodape_cartao(""))
            return

        ids = msg.get("ids_evidencias", [])
        contagem = f"{len(ids)} evidência{'s' if len(ids) != 1 else ''} · {msg.get('hora', '')}"
        st.html(ui.cabecalho_cartao("ia", "Resposta", ui.badge("IA"), contagem))
        if msg["conteudo"]:
            st.markdown(ui.markdown_seguro(msg["conteudo"]))
        if ids:
            chips = "".join(ui.chip(eid) for eid in ids)
            st.html(f'<div class="cp-evidencias-usadas">{chips}<span>Evidências consideradas nesta resposta</span></div>')

        telemetria = msg.get("telemetria") or {}
        st.html(ui.rodape_cartao(
            f'{ui.icone("info", 11)}Síntese da IA · revisão humana pendente',
            f'<span class="cp-rodape-mono">{escape(formatar_telemetria(telemetria))}</span>',
        ))
        rastro = telemetria.get("rastro_ferramentas", [])
        if rastro:
            with st.expander(f"Ver raciocínio e fontes · {len(rastro)} ferramenta{'s' if len(rastro) != 1 else ''}"):
                for idx, tool in enumerate(rastro, start=1):
                    st.markdown(f"**{idx}. Ferramenta:** `{tool['ferramenta']}` ({tool.get('duracao_ms', 0)}ms)")
                    st.json({"argumentos": tool["argumentos"], "resultado_banco": tool["resultado"]})


# ---------- Barra lateral: marca, entradas e evidencias da sessao ----------
with st.sidebar:
    st.html(ui.logo())
    st.html(ui.bloco_squad("Squad Caixa-Preta", "Auditoria de Infra e TI"))

    st.html(ui.eyebrow("Entradas multimodais"))
    chave = st.session_state["chave_uploader"]
    gravacao = st.audio_input("Gravar relato do incidente", key=f"gravacao_{chave}")
    uploads = st.file_uploader(
        "Enviar arquivos (prints e áudios)",
        type=EXTENSOES_IMAGEM + EXTENSOES_AUDIO,
        accept_multiple_files=True,
        key=f"arquivos_{chave}",
    )
    st.caption("Dica: você também pode arrastar arquivos ou gravar áudio direto no campo do chat.")

    st.html(ui.eyebrow("Evidências da sessão"))
    lista_lateral = st.empty()  # preenchida depois que os uploads forem processados

    st.html(ui.eyebrow("Exemplos de pergunta"))
    st.markdown(
        "- Qual o custo de 4 unidades do item A101?\n"
        "- O que o print mostra e o que o áudio relata?\n"
        "- O valor do print bate com o do áudio?"
    )
    st.divider()
    if chave_configurada():
        st.html(ui.indicador(f"Gemini {MODEL} · Whisper {WHISPER_MODEL}", "ok"))
    else:
        st.html(ui.indicador("GEMINI_API_KEY ausente no .env", "atencao"))
    st.button("Limpar sessão e cache", width="stretch", on_click=limpar_sessao)

# ---------- Topbar e cabecalho (preenchidos no fim, quando o estado ja e conhecido) ----------
topo = st.container(key="topbar", horizontal=True, vertical_alignment="center")
cabecalho = st.container()

# ---------- Evidencias da barra lateral ----------
itens_laterais: list[ItemEvidencia] = []
arquivos_laterais = list(uploads or []) + ([gravacao] if gravacao else [])
for arquivo in arquivos_laterais:
    tipo = tipo_do_arquivo(arquivo)
    if tipo is None:
        st.warning(f"Formato nao suportado: {arquivo.name}")
        continue
    nome = "Gravação do microfone" if arquivo is gravacao else arquivo.name
    item, erro = processar_upload(arquivo, tipo, nome, canal="lateral")
    if erro:
        st.warning(erro)
        continue
    itens_laterais.append(item)
    cartao_evidencia(item, "lateral")

# Ativas = barra lateral (como esta agora) + tudo que veio pelo chat, sem repetir o mesmo arquivo
itens_ativos = list({i.id: i for i in itens_laterais + st.session_state["itens_chat"]}.values())
st.session_state["itens_ativos"] = itens_ativos
st.session_state["evidencias_ativas"] = [i.evidencia for i in itens_ativos]

# Auditoria de conflito entre o que a imagem mostra e o que o audio diz
visao = next((i.evidencia for i in itens_ativos if i.tipo == "imagem"), None)
audio = next((i.evidencia for i in itens_ativos if i.tipo == "audio"), None)
auditoria = auditar_conflito_evidencias(visao, audio) if visao and audio else None

# ---------- Conversa ----------
historico = st.session_state["historico_mensagens"]
if not historico and not itens_laterais:
    with st.container(key="cartao-inicio", gap="small"):
        st.html(ui.cabecalho_cartao("ia", "Como começar", ui.badge("IA")))
        st.markdown(
            "Junte as evidências do incidente e pergunte. Cada conclusão aponta para a fonte "
            "(print, áudio ou catálogo).\n\n"
            "- **Barra lateral:** grave o relato pelo microfone ou envie vários prints e áudios.\n"
            "- **Campo do chat:** arraste arquivos, anexe pelo clipe ou grave pelo microfone.\n"
            "- **Só um áudio, sem texto:** o pedido feito no áudio vira a pergunta."
        )
        st.html(ui.rodape_cartao(f"{ui.icone('info', 11)}Prints e áudios ficam só nesta sessão até você limpar"))

for indice, msg in enumerate(historico):
    if msg["papel"] == "user":
        st.html(ui.pergunta(msg["conteudo"], msg.get("hora", "")))
        for anexo in msg.get("anexos", []):
            item = registro.por_id(anexo["id"]) if anexo.get("id") else None
            if item:
                cartao_evidencia(item, f"msg{indice}")
            if anexo.get("erro"):
                st.warning(anexo["erro"])
    else:
        cartao_resposta(msg, indice)

# Retry: reenvia a ultima pergunta que falhou (ex.: internet oscilou durante a demo)
pergunta_falhou = st.session_state["ultima_pergunta_falhou"]
if pergunta_falhou and st.button("Tentar novamente", icon=":material/refresh:"):
    st.session_state["historico_mensagens"].pop()  # remove a mensagem de falha
    responder(pergunta_falhou)
    st.rerun()

# Indice de evidencias (estado aberto/fechado de verdade, nao camadas escondidas)
ids_ativos = {i.id for i in itens_ativos}
if len(registro):
    with st.container(key="acordeao-evidencias"):
        with st.expander(f"**Evidências** · {len(ids_ativos)} ativas · {len(registro)} na sessão"):
            linhas = "".join(ui.linha_evidencia(i, i.id in ids_ativos) for i in registro.todos())
            st.html(
                f"{linhas}<div class='cp-custodia'>{ui.icone('info', 11)}"
                "Cada arquivo é identificado pelo hash SHA-256 do conteúdo enviado</div>"
            )
st.html(ui.linha_contexto([i.id for i in itens_ativos]))

# ---------- Preenche topbar, cabecalho e lista lateral ----------
if auditoria and auditoria["divergencia_identificada"]:
    status = ("Divergência", "alerta")
elif itens_ativos or historico:
    status = ("Em análise", "analise")
else:
    status = ("Aguardando evidências", "neutro")

inicio = st.session_state["inicio_sessao"]
with topo:
    st.html(ui.topbar(f"SESSÃO {inicio:%H:%M}", *status))
    st.download_button(
        "Relatório",
        data=gerar_relatorio(inicio, registro.todos(), ids_ativos, auditoria, historico),
        file_name=f"relatorio_caixa-preta_{inicio:%Y%m%d-%H%M}.md",
        mime="text/markdown",
        type="primary",
        key="relatorio",
        disabled=not (len(registro) or historico),
        on_click="ignore",
    )

with cabecalho:
    total = len(itens_ativos)
    meta = [
        f"{inicio:%d} {MESES[inicio.month - 1]} {inicio:%Y} · {inicio:%H:%M}",
        f"{total} evidência{'s' if total != 1 else ''} ativa{'s' if total != 1 else ''}",
    ]
    if auditoria and not auditoria["divergencia_identificada"]:
        meta.append(ui.indicador("Imagem e áudio consistentes", "ok"))
    st.html(ui.cabecalho_pagina("Auditoria de Infraestrutura e TI", meta))
    if auditoria and auditoria["divergencia_identificada"]:
        st.html(ui.callout(
            "DIVERGÊNCIA ENTRE IMAGEM E ÁUDIO",
            "Confirme com um humano antes de agir",
            " | ".join(auditoria["divergencias"]) + ". Nenhuma fonte foi descartada.",
            tom="alerta",
        ))

with lista_lateral.container():
    if len(registro):
        st.html('<div class="cp-lista">' + "".join(
            ui.item_lateral(i, i.id in ids_ativos) for i in reversed(registro.todos())
        ) + "</div>")
    else:
        st.html('<div class="cp-lista-vazia">Nenhuma evidência ainda.</div>')

# Campo de Entrada: aceita texto, arquivos arrastados/anexados e gravacao pelo microfone
envio = st.chat_input(
    "Pergunte sobre este incidente ou arraste um print/áudio…",
    accept_file="multiple",
    file_type=EXTENSOES_IMAGEM + EXTENSOES_AUDIO,
    accept_audio=True,
)
if envio:
    texto = (envio.text or "").strip()
    arquivos_chat = list(envio.files or []) + ([envio.audio] if envio.audio else [])

    anexos = []
    for arquivo in arquivos_chat:
        tipo = tipo_do_arquivo(arquivo)
        nome = "Gravação do microfone" if arquivo is envio.audio else arquivo.name
        if tipo is None:
            anexos.append({"nome": nome, "erro": f"Formato nao suportado: {nome}"})
            continue
        item, erro = processar_upload(arquivo, tipo, nome, canal="chat")
        anexos.append({"nome": nome, "id": item.id if item else None, "erro": erro})
        if item and item.id not in {i.id for i in st.session_state["itens_chat"]}:
            st.session_state["itens_chat"].append(item)

    st.session_state["historico_mensagens"].append({
        "papel": "user", "conteudo": texto, "anexos": anexos, "hora": f"{datetime.now():%H:%M}",
    })
    itens_ativos = list({i.id: i for i in itens_laterais + st.session_state["itens_chat"]}.values())
    st.session_state["itens_ativos"] = itens_ativos
    st.session_state["evidencias_ativas"] = [i.evidencia for i in itens_ativos]

    # So arquivo/audio, sem texto: o pedido esta nas proprias evidencias (ex.: relato gravado)
    if texto or any(a.get("id") for a in anexos):
        responder(texto or PERGUNTA_PADRAO)
    st.rerun()
