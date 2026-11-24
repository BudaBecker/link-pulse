import re
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from pydantic import (
    AwareDatetime,
    BaseModel,
    Field,
    HttpUrl,
    PrivateAttr,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)

URL_HTTP = TypeAdapter(HttpUrl)

# Aceita "2026-12-25T23:59:59Z" e "2026-12-25T20:59:59-03:00"; recusa "1798243200" e "25/12/2026".
INICIO_DATA_ISO = re.compile(r"\d{4}-\d\d-\d\dT")
ALEM_DO_MICROSSEGUNDO = re.compile(r"(?<=\.\d{6})\d+")


# Sem isso, o Pydantic aceitaria um timestamp Unix, em número ou em texto.
def exigir_data_iso(valor: object) -> object:
    if valor is not None and not (isinstance(valor, str) and INICIO_DATA_ISO.match(valor)):
        raise ValueError("a data deve estar em ISO 8601 com fuso")
    return valor


class NovoCliente(BaseModel):
    nome: str = Field(min_length=1)


class NovaCampanha(BaseModel):
    cliente_id: str = Field(min_length=1)
    nome: str = Field(min_length=1)
    descricao: str | None = None
    tags: list[str] = []


class NovoLink(BaseModel):
    url: str
    cliente_id: str = Field(min_length=1)
    canal: str | None = None
    expira_em: AwareDatetime | None = None
    campanha_id: str | None = None

    # O HttpUrl só confere: devolver o texto original evita gravar a URL normalizada por ele.
    @field_validator("url")
    @classmethod
    def validar_url(cls, valor: str) -> str:
        try:
            URL_HTTP.validate_python(valor)
            
        except ValidationError:
            raise ValueError("url deve ser absoluta, http ou https, com host válido") from None
        
        # O HttpUrl corrige "https:/host" e "https:///host"; o texto gravado precisa ter o host.
        if not urlsplit(valor).hostname:
            raise ValueError("url deve ter host")
        # O HttpUrl remove ou codifica espaços, mas o texto gravado os manteria.
        if any(c.isspace() for c in valor):
            raise ValueError("url não pode ter espaços; use %20")
        return valor

    @field_validator("expira_em", mode="before")
    @classmethod
    def validar_expira_em(cls, valor: object) -> object:
        return exigir_data_iso(valor)


def truncar_no_milissegundo(momento: datetime) -> datetime:
    return momento.replace(microsecond=momento.microsecond // 1000 * 1000)


class Janela(BaseModel):
    inicio: AwareDatetime
    fim: AwareDatetime
    _resto_inicio: str = PrivateAttr("")
    _resto_fim: str = PrivateAttr("")

    @field_validator("inicio", "fim", mode="before")
    @classmethod
    def validar_datas(cls, valor: object) -> object:
        return exigir_data_iso(valor)

    # O datetime descarta a fração além do microssegundo; ela fica em texto para comparar e arredondar.
    @model_validator(mode="wrap")
    @classmethod
    def preservar_fracao(cls, dados: object, handler) -> "Janela":
        restos = {}
        if isinstance(dados, dict):
            dados = dict(dados)
            for campo in ("inicio", "fim"):
                valor = dados.get(campo)
                if isinstance(valor, str) and (resto := ALEM_DO_MICROSSEGUNDO.search(valor)):
                    restos[campo] = resto.group().rstrip("0")
                    dados[campo] = valor[: resto.start()] + valor[resto.end() :]

        janela = handler(dados)
        janela._resto_inicio = restos.get("inicio", "")
        janela._resto_fim = restos.get("fim", "")
        tamanho = max(len(janela._resto_inicio), len(janela._resto_fim))
        inicio = (janela.inicio, janela._resto_inicio.ljust(tamanho, "0"))
        fim = (janela.fim, janela._resto_fim.ljust(tamanho, "0"))
        if inicio > fim:
            raise ValueError("inicio deve ser anterior ou igual a fim")
        return janela

    # O Cassandra guarda milissegundos: o início sobe e o fim desce até o milissegundo incluído.
    @property
    def milissegundos_incluidos(self) -> tuple[datetime, datetime]:
        primeiro = truncar_no_milissegundo(self.inicio)
        if primeiro < self.inicio or self._resto_inicio:
            primeiro += timedelta(milliseconds=1)
        return primeiro, truncar_no_milissegundo(self.fim)


class JanelaDoLink(Janela):
    short_code: str = Field(min_length=1)


class JanelaDoCliente(Janela):
    cliente_id: str = Field(min_length=1)
