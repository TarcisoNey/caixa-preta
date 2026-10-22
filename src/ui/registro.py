"""Registro das evidencias da sessao, do lado da interface.

Guarda o que a UI precisa e o contrato EvidenciaMultimodal nao tem (ID exibido, nome do
arquivo, hash SHA-256, bytes originais, forma de onda), sem alterar o contrato.
Tambem funciona como cache: o mesmo arquivo nao passa de novo pelo Whisper/Gemini.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime

from src.core.contracts import EvidenciaMultimodal
from src.ui.midia import FormaDeOnda


@dataclass
class ItemEvidencia:
    """Uma evidencia ja processada, com os metadados exibidos na tela e no relatorio."""

    id: str  # "E01", "E02"... estavel durante a sessao
    nome: str
    tipo: str  # "imagem" | "audio"
    sha256: str
    dados: bytes
    evidencia: EvidenciaMultimodal
    canal: str  # "lateral" (barra lateral) | "chat" (campo do chat)
    recebida_em: datetime = field(default_factory=datetime.now)
    forma_de_onda: FormaDeOnda | None = None

    @property
    def hash_curto(self) -> str:
        return self.sha256[:6]

    @property
    def rotulo_tipo(self) -> str:
        return "Print" if self.tipo == "imagem" else "Áudio"

    @property
    def tamanho_legivel(self) -> str:
        tamanho = len(self.dados)
        if tamanho >= 1_000_000:
            return f"{tamanho / 1_000_000:.1f} MB".replace(".", ",")
        return f"{max(tamanho // 1000, 1)} KB"


def chave_do_arquivo(tipo: str, dados: bytes) -> tuple[str, str]:
    """Devolve (chave do cache, sha256) para um arquivo enviado."""
    sha256 = hashlib.sha256(dados).hexdigest()
    return f"{tipo}:{sha256}", sha256


class RegistroEvidencias:
    """Evidencias da sessao, na ordem em que chegaram. IDs nunca sao reaproveitados."""

    def __init__(self) -> None:
        self._itens: dict[str, ItemEvidencia] = {}

    def buscar(self, chave: str) -> ItemEvidencia | None:
        return self._itens.get(chave)

    def registrar(self, chave: str, **campos) -> ItemEvidencia:
        """Cria o item com o proximo ID livre (E01, E02...). Se a chave ja existe, devolve o existente."""
        if chave in self._itens:
            return self._itens[chave]
        item = ItemEvidencia(id=f"E{len(self._itens) + 1:02d}", **campos)
        self._itens[chave] = item
        return item

    def por_id(self, eid: str) -> ItemEvidencia | None:
        return next((i for i in self._itens.values() if i.id == eid), None)

    def todos(self) -> list[ItemEvidencia]:
        return list(self._itens.values())

    def limpar(self) -> None:
        self._itens.clear()

    def __len__(self) -> int:
        return len(self._itens)
