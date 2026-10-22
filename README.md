# OmniAssistant — Squad Caixa-Preta

**Caixa-Preta** (Squad 1): assim como o gravador de voo, o assistente junta áudio e evidências para explicar o que aconteceu num incidente.

Assistente multimodal de **Auditoria de Infraestrutura e TI**: recebe prints de consoles cloud, áudios relatando incidentes e comandos em texto, e transforma tudo em evidências estruturadas para apoiar a auditoria.

Sprint 3 — Multimodalidade (Visão + Áudio Whisper) · DataLakers + Navi Hub (Tecnopuc)

**Versão atual:** `v1.0-rc` (ingestão multimodal, agente com ferramentas SQLite e interface Streamlit)

## Integrantes

| Nome |
| --- |
| Tarciso Mota Ney da Silva | 


Papéis: **Piloto** (teclado) · **Copiloto** (revisão e testes em tempo real) · **Arquiteto** (documentação e consistência dos contratos).

## Arquitetura

Os módulos não se conhecem entre si: conversam apenas pelos contratos de `src/core/contracts.py`.

```
 print de cloud ──► src/vision ──┐
                                 ├──► EvidenciaMultimodal ──► agente / tools ──► app (Streamlit)
 áudio incidente ─► src/audio ───┘
        ▲
   EntradaUsuario (imagem | audio | texto)
```

```
.
├── src/
│   ├── core/
│   │   ├── config.py       # segredos, modelo e timeout (único lugar que lê o .env)
│   │   ├── contracts.py    # EntradaUsuario, SegmentoFala, EvidenciaMultimodal
│   │   ├── ingestion.py    # despachante com lazy loading + detector de conflito
│   │   └── agent.py        # loop agêntico com function calling no Gemini
│   ├── vision/processor.py # análise de prints e diagramas (Gemini)
│   ├── audio/processor.py  # transcrição de áudios (Whisper local)
│   └── tools/local.py      # catálogo SQLite somente leitura + cálculos
├── data/                   # mídias de demonstração produzidas pelo trio
├── tests/
│   ├── smoke_test_omni.py
│   ├── test_resiliencia_config.py
│   ├── test_resiliencia_ingestao.py
│   ├── test_fluxo_completo.py
│   └── test_resiliencia_ui.py
├── app.py                  # interface Streamlit
├── .env.example
├── requirements.txt
└── README.md
```

### Contratos

| Classe | Para que serve | Regras |
| --- | --- | --- |
| `EntradaUsuario` | O que o usuário enviou | texto não vazio; imagem/áudio exigem arquivo existente |
| `SegmentoFala` | Trecho transcrito com tempo | tempos ≥ 0; fim ≥ início; texto não vazio |
| `EvidenciaMultimodal` | Informação extraída, pronta para o agente | origem ∈ {visao, audio, texto, banco_dados}; confiança entre 0 e 1 |

Todas herdam de `ContratoBase` (`extra="forbid"`): campo não declarado gera erro.

## Como rodar

Requer Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env             # Windows: copy .env.example .env
# edite o .env e coloque sua GEMINI_API_KEY
```

### Comandos de verificação

```bash
python -m src.core.config                 # status da configuração (sem expor a chave)
python -m src.core.contracts              # valida contratos + teste negativo de timestamp
python -m tests.smoke_test_omni           # smoke test só dos contratos
python -m tests.smoke_test_omni --api     # smoke test + ping real no Gemini
python -m tests.test_resiliencia_config   # garante erro claro quando falta a chave
python -m tests.test_resiliencia_ingestao # lazy loading, midia corrompida/silenciosa e conflitos
python -m tests.test_fluxo_completo --offline # guardrails: SQL injection, banco read-only, allowlist de tools
python -m tests.test_fluxo_completo       # guardrails + fluxo completo com o Gemini
python -m tests.test_resiliencia_ui       # entradas vazias viram aviso amigável na UI
```

### Interface (v1.0)

```bash
streamlit run app.py                      # abre em http://localhost:8501
```

Na barra lateral, envie um print e/ou um áudio e pergunte no chat. Cada resposta traz o tempo, os turnos e os tokens. O painel **Auditoria de Ferramentas** mostra cada chamada ao catálogo com os argumentos e o resultado. Se o print e o áudio citarem valores diferentes, um aviso de divergência aparece acima do chat. Se a API falhar, o botão **Tentar novamente** reenvia a pergunta.

### Pipeline de ingestão (v0.2)

```bash
python -m src.core.ingestion texto --texto "Qual o status do cluster de producao?"
python -m src.core.ingestion imagem --caminho data/prints/alarme_cpu.png
python -m src.core.ingestion audio --caminho data/audios/relato.m4a
python -m src.core.ingestion conflito --imagem data/prints/pedido.png --audio data/audios/estorno.m4a
```

O modo `conflito` compara valores monetários, percentuais e horários entre o print e o áudio. Se as duas fontes citarem valores diferentes, ele sinaliza a divergência para decisão humana sem descartar nenhuma das duas.

### Agente e ferramentas (v0.3)

```bash
python -m src.tools.local                 # cria data/catalogo.sqlite e testa A101 (4 x R$ 25,00 = R$ 100,00)
python -m src.core.agent                  # pergunta de exemplo: consulta o catálogo e calcula o total
```

O agente só executa ferramentas da allowlist (`consultar_item`, `calcular_total`, `validar_codigo`), com argumentos validados por schemas Pydantic estritos. O banco abre em modo somente leitura, e códigos fora do padrão `A101` são recusados antes de chegar ao SQL.

Resultado esperado do smoke test com `--api`: `"status_contratos": "PASS"` e `"conexao_api": "CONECTADO_COM_SUCESSO"`.

Para trocar o modelo sem mexer no código, defina `GEMINI_MODEL` no `.env`.

## Segurança

- O `.env` está no `.gitignore` e **nunca** deve ser commitado. Confira com `git status` antes de cada commit.
- O status de configuração só informa se a chave está `configurada` ou `AUSENTE`.
- Prints em `data/` devem ter IDs de conta, IPs e e-mails apagados antes do commit.

## Fluxo Git do trio

- `main` sempre funcionando: cada feature numa branch (`feat/vision`, `feat/audio`, …) e merge via Pull Request.
- Antes de abrir PR: rodar o smoke test.
- Commits no padrão `tipo(escopo): descrição` — ex.: `feat(audio): transcrição com timestamps`.
