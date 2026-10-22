"""Interface web do OmniAssistant (Squad Caixa-Preta).

Uso:
    streamlit run app.py
"""

import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory

import streamlit as st

from src.core.contracts import EntradaUsuario, EvidenciaMultimodal
from src.core.ingestion import auditar_conflito_evidencias, despachar_ingestao
from src.core.agent import executar_agente
from src.tools.local import inicializar_banco

# Configuracao da Pagina
st.set_page_config(page_title="OmniAssistant | Caixa-Preta", layout="wide", initial_sidebar_state="expanded")

# Inicializa o banco SQLite local
inicializar_banco()

# Inicializacao do Estado da Sessao (Session State)
st.session_state.setdefault("historico_mensagens", [])
st.session_state.setdefault("evidencias_ativas", [])
# Cache de evidencias por hash do arquivo: evita rodar Whisper/Gemini de novo a cada interacao
st.session_state.setdefault("cache_evidencias", {})
st.session_state.setdefault("ultima_pergunta_falhou", None)
# Trocar a chave dos uploaders e o jeito de limpa-los no Streamlit
st.session_state.setdefault("chave_uploader", 0)


def processar_upload(arquivo, tipo: str) -> EvidenciaMultimodal | None:
    """Ingere um upload (com cache por conteudo) e mostra erros sem derrubar a tela."""
    dados = arquivo.getvalue()
    chave = f"{tipo}:{hashlib.sha256(dados).hexdigest()}"
    cache = st.session_state["cache_evidencias"]
    if chave in cache:
        return cache[chave]

    rotulo = "Analisando print com o Gemini..." if tipo == "imagem" else "Transcrevendo audio com o Whisper..."
    with st.spinner(rotulo), TemporaryDirectory() as tmp_dir:
        caminho_tmp = Path(tmp_dir) / Path(arquivo.name).name
        caminho_tmp.write_bytes(dados)
        try:
            evidencia = despachar_ingestao(EntradaUsuario(tipo=tipo, caminho_arquivo=caminho_tmp))
        except ValueError as e:
            # Problema no arquivo enviado: aviso amigavel para o usuario corrigir
            st.warning(f"Nao foi possivel usar este arquivo: {e}")
            return None
        except Exception as e:
            st.error(f"Falha ao processar {tipo} ({type(e).__name__}). Verifique a conexao e tente de novo.")
            return None

    cache[chave] = evidencia
    return evidencia


def responder(pergunta: str) -> None:
    """Roda o agente e guarda a resposta (ou a falha, para permitir retry) no historico."""
    with st.spinner("OmniAssistant raciocinando e consultando ferramentas..."):
        try:
            resultado = executar_agente(pergunta, st.session_state["evidencias_ativas"])
            st.session_state["historico_mensagens"].append({
                "papel": "assistant",
                "conteudo": resultado["resposta"],
                "telemetria": resultado,
            })
            st.session_state["ultima_pergunta_falhou"] = None
        except Exception as e:
            st.session_state["historico_mensagens"].append({
                "papel": "assistant",
                "conteudo": f"Falha na execucao: {type(e).__name__} - {e}",
                "erro": True,
            })
            st.session_state["ultima_pergunta_falhou"] = pergunta


st.title("OmniAssistant: Auditoria de Infraestrutura e TI")
st.caption(
    "Squad Caixa-Preta: assim como o gravador de voo, juntamos prints de console e audios de "
    "incidente para explicar o que aconteceu, com cada conclusao rastreavel ate a sua fonte."
)

# Barra Lateral: Uploads e Configuracoes
with st.sidebar:
    st.header("Entradas Multimodais")
    chave = st.session_state["chave_uploader"]
    upload_img = st.file_uploader(
        "Print de console / monitoramento / diagrama", type=["png", "jpg", "jpeg"], key=f"img_{chave}"
    )
    upload_audio = st.file_uploader(
        "Audio relatando o incidente", type=["wav", "mp3", "ogg", "m4a"], key=f"audio_{chave}"
    )

    if st.button("Limpar Sessao e Cache", width="stretch"):
        st.session_state["historico_mensagens"].clear()
        st.session_state["evidencias_ativas"].clear()
        st.session_state["cache_evidencias"].clear()
        st.session_state["ultima_pergunta_falhou"] = None
        st.session_state["chave_uploader"] += 1
        st.rerun()

    st.divider()
    st.caption("Exemplos de pergunta")
    st.markdown(
        "- Qual o custo de 4 unidades do item A101?\n"
        "- O que o print mostra e o que o audio relata?\n"
        "- O valor do print bate com o do audio?"
    )

# Processamento de Uploads com Cache
novas_evidencias = []
col_preview1, col_preview2 = st.columns(2)

if upload_img:
    with col_preview1:
        st.subheader("Preview da Imagem")
        st.image(upload_img, width="stretch")
        ev_img = processar_upload(upload_img, "imagem")
        if ev_img:
            novas_evidencias.append(ev_img)
            with st.expander("Leitura do Gemini"):
                st.write(ev_img.resumo_informacao)
                st.caption(f"Confianca declarada: {ev_img.confianca_declarada:.0%}")

if upload_audio:
    with col_preview2:
        st.subheader("Preview do Audio")
        st.audio(upload_audio)
        ev_audio = processar_upload(upload_audio, "audio")
        if ev_audio:
            novas_evidencias.append(ev_audio)
            with st.expander("Transcricao Whisper", expanded=True):
                st.write(ev_audio.resumo_informacao)
                for seg in ev_audio.segmentos_audio:
                    st.caption(f"[{seg.inicio_segundos:.1f}s - {seg.fim_segundos:.1f}s] {seg.texto_transcrito}")

st.session_state["evidencias_ativas"] = novas_evidencias

# Auditoria de conflito entre o que a imagem mostra e o que o audio diz
visao = next((e for e in novas_evidencias if e.origem == "visao"), None)
audio = next((e for e in novas_evidencias if e.origem == "audio"), None)
if visao and audio:
    auditoria = auditar_conflito_evidencias(visao, audio)
    if auditoria["divergencia_identificada"]:
        st.warning(
            "**Divergencia entre imagem e audio.** "
            + " | ".join(auditoria["divergencias"])
            + ". Nenhuma fonte foi descartada: confirme com um humano antes de agir."
        )
    else:
        st.success("Imagem e audio consistentes ou complementares.")

# Renderizacao Enriquecida com Painel XAI
for msg in st.session_state["historico_mensagens"]:
    with st.chat_message(msg["papel"]):
        if msg.get("erro"):
            st.error(msg["conteudo"])
        else:
            st.markdown(msg["conteudo"])

        # Se for mensagem do assistente e contiver telemetria, exibe os detalhes
        telemetria = msg.get("telemetria")
        if telemetria:
            tempo_ms = telemetria.get("tempo_total_ms", 0)
            tokens = telemetria.get("tokens_estimados", "N/A")
            turnos = telemetria.get("total_turnos", 1)

            st.caption(f"Tempo de Execucao: {tempo_ms}ms | Turnos Agenticos: {turnos} | Tokens: {tokens}")

            rastro = telemetria.get("rastro_ferramentas", [])
            if rastro:
                with st.expander(f"Auditoria de Ferramentas ({len(rastro)} acoes executadas)"):
                    for idx, tool in enumerate(rastro, start=1):
                        st.markdown(f"**{idx}. Ferramenta:** `{tool['ferramenta']}` ({tool.get('duracao_ms', 0)}ms)")
                        st.json({"argumentos": tool["argumentos"], "resultado_banco": tool["resultado"]})

# Retry: reenvia a ultima pergunta que falhou (ex.: internet oscilou durante a demo)
pergunta_falhou = st.session_state["ultima_pergunta_falhou"]
if pergunta_falhou and st.button("Tentar novamente"):
    st.session_state["historico_mensagens"].pop()  # remove a mensagem de falha
    responder(pergunta_falhou)
    st.rerun()

# Campo de Entrada de Mensagem
comando_chat = st.chat_input("Pergunte sobre as evidencias ou peca uma acao...")
if comando_chat:
    st.session_state["historico_mensagens"].append({"papel": "user", "conteudo": comando_chat})
    responder(comando_chat)
    st.rerun()
