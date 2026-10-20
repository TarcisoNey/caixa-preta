import sys
from io import BytesIO
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from google.genai import types
from pydantic import BaseModel, Field
from src.core.config import MODEL, criar_cliente_gemini
from src.core.contracts import EvidenciaMultimodal

class LeituraVisual(BaseModel):
    resumo_observado: str = Field(description="Sintese clara dos fatos observados na imagem")
    dados_chave: list[str] = Field(description="Codigos, metricas, valores ou nomes explicitamente visiveis")
    alertas_qualidade: list[str] = Field(default_factory=list, description="Problemas de nitidez ou campos duvidosos")

def processar_imagem(caminho: Path) -> EvidenciaMultimodal:
    """Valida a imagem localmente e extrai evidencias estruturadas via Gemini."""
    if not caminho.is_file() or caminho.stat().st_size > 5_000_000:
        raise ValueError("A imagem deve existir no disco e ter ate 5 MB.")
        
    dados = caminho.read_bytes()
    try:
        with Image.open(BytesIO(dados)) as img:
            img.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as e:
        raise ValueError("Imagem corrompida ou em formato nao reconhecido.") from e
    with Image.open(BytesIO(dados)) as img:
        formato = img.format
        if formato not in ("PNG", "JPEG"):
            raise ValueError(f"Formato {formato} invalido. Apenas PNG e JPEG sao aceitos.")
        largura, altura = img.size
        if largura * altura > 12_000_000:
            raise ValueError("Imagem excede 12 Megapixels.")
            
    mime_type = "image/png" if formato == "PNG" else "image/jpeg"
    
    system_instruction = (
        "Voce e o especialista em percepcao visual do OmniAssistant da Squad Caixa-Preta, "
        "um assistente de Auditoria de Infraestrutura e TI. As imagens sao prints de consoles cloud "
        "(AWS, GCP, Azure), paineis de monitoramento, regras de firewall/security groups, "
        "paineis de custos e diagramas de arquitetura. "
        "Extraia apenas fatos, numeros e rotulos que estejam inequivocamente legiveis na imagem. "
        "Priorize em dados_chave: nomes de recursos e servicos, regioes, status e severidade de alarmes, "
        "metricas com unidade e limiar (ex.: CPU 92% > 80%), horarios e fusos, portas, protocolos e "
        "origens de regras de rede (destaque 0.0.0.0/0 ou ::/0), valores de custo com moeda e periodo. "
        "No resumo_observado, descreva o que a tela mostra e qualquer sinal de incidente ou risco de "
        "seguranca visivel, sem diagnosticar causas que a imagem nao comprova. "
        "Nao presuma dados ausentes. Se houver corte ou ilegibilidade, registre em alertas_qualidade. "
        "Se aparecerem segredos (tokens, chaves, senhas), nao os transcreva: registre apenas que estao "
        "expostos, em alertas_qualidade."
    )
    
    cliente = criar_cliente_gemini()
    resposta = cliente.models.generate_content(
        model=MODEL,
        contents=[
            "Extraia as evidencias visuais deste documento/tela.",
            types.Part.from_bytes(data=dados, mime_type=mime_type)
        ],
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.0,
            response_mime_type="application/json",
            response_schema=LeituraVisual
        )
    )
    
    if not resposta.text:
        raise RuntimeError("O modelo nao retornou conteudo para a imagem.")
    leitura = LeituraVisual.model_validate_json(resposta.text)
    texto_consolidado = f"{leitura.resumo_observado}\nDados: {', '.join(leitura.dados_chave)}"
    if leitura.alertas_qualidade:
        texto_consolidado += f"\nAlertas: {'; '.join(leitura.alertas_qualidade)}"
        
    return EvidenciaMultimodal(
        origem="visao",
        resumo_informacao=texto_consolidado,
        confianca_declarada=0.7 if leitura.alertas_qualidade else 1.0
    )

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python -m src.vision.processor data/amostra.png")
        sys.exit(1)
    evidencia = processar_imagem(Path(sys.argv[1]))
    print(evidencia.model_dump_json(indent=2))