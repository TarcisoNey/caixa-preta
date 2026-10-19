# OmniAssistant — Squad Caixa-Preta

**Caixa-Preta** (Squad 1): assim como o gravador de voo, o assistente junta áudio e evidências para explicar o que aconteceu num incidente.

Assistente multimodal de **Auditoria de Infraestrutura e TI**: recebe prints de consoles cloud, áudios relatando incidentes e comandos em texto, e transforma tudo em evidências estruturadas para apoiar a auditoria.

Sprint 3 — Multimodalidade (Visão + Áudio Whisper) · DataLakers + Navi Hub (Tecnopuc)

**Versão atual:** `v0.1-setup` (arquitetura modular, contratos Pydantic e smoke test)

## Integrantes

| Nome | Papel hoje (rotativo) |
| --- | --- |
| Maria Eduarda Melloni | _a definir_ |
| _(integrante 2)_ | _a definir_ |
| _(integrante 3)_ | _a definir_ |

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
│   │   └── contracts.py    # EntradaUsuario, SegmentoFala, EvidenciaMultimodal
│   ├── vision/             # análise de prints e diagramas
│   ├── audio/              # transcrição de áudios (Whisper)
│   └── tools/              # ferramentas do agente
├── data/                   # mídias de demonstração produzidas pelo trio
├── tests/
│   ├── smoke_test_omni.py
│   └── test_resiliencia_config.py
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
```

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
