import re
from urllib.parse import urlsplit

from pydantic import (
    AwareDatetime,
    BaseModel,
    Field,
    HttpUrl,
    TypeAdapter,
    ValidationError,
    field_validator,
)

URL_HTTP = TypeAdapter(HttpUrl)

# Aceita "2026-12-25T23:59:59Z" e "2026-12-25T20:59:59-03:00"; recusa "1798243200" e "25/12/2026".
INICIO_DATA_ISO = re.compile(r"\d{4}-\d\d-\d\dT")


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
        
        # O HttpUrl ignora espaços nas pontas, mas o texto gravado os manteria.
        # O HttpUrl corrige "https:/host" e "https:///host"; o texto gravado precisa ter o host.
        if not urlsplit(valor).hostname:
            raise ValueError("url deve ter host")
        if valor != valor.strip():
            raise ValueError("url não pode ter espaços no início ou no fim")
        return valor

    # Sem isso, o Pydantic aceitaria um timestamp Unix, em número ou em texto.
    @field_validator("expira_em", mode="before")
    @classmethod
    def exigir_data_iso(cls, valor: object) -> object:
        if valor is not None and not (isinstance(valor, str) and INICIO_DATA_ISO.match(valor)):
            raise ValueError("expira_em deve ser uma data em ISO 8601 com fuso")
        return valor
