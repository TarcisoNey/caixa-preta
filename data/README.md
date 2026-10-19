# data/ — dados de demonstração da Squad Caixa-Preta

Mídias produzidas pelo próprio trio para o cenário de **Auditoria de Infraestrutura e TI**.
Nada de mídia externa pronta.

## Sugestão de organização

```
data/
├── prints/     # capturas de console cloud e monitoramento
└── audios/     # mensagens de voz gravadas pelo trio relatando incidentes
```

### Ideias de prints (visão)
- Alarme de CPU/memória disparado num painel de monitoramento
- Regra de firewall / security group liberando porta para `0.0.0.0/0`
- Painel de custos com pico inesperado
- Diagrama de arquitetura desenhado pelo trio (Excalidraw)

### Ideias de áudios (Whisper)
- Plantonista relatando "o serviço X caiu às 3h, reiniciei o pod e voltou"
- Pedido de auditoria: "verifica se tem bucket público na conta de produção"
- Relato com horários, para testar `SegmentoFala` (timestamps)

> Atenção: antes de commitar um print real, apague IDs de conta, IPs, e-mails e qualquer token visível.
