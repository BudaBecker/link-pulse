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
    model_validator,
)

URL_HTTP = TypeAdapter(HttpUrl)

# Aceita "2026-12-25T23:59:59Z" e "2026-12-25T20:59:59-03:00"; recusa "1798243200" e "25/12/2026".
INICIO_DATA_ISO = re.compile(r"\d{4}-\d\d-\d\dT")


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


class Janela(BaseModel):
    inicio: AwareDatetime
    fim: AwareDatetime

    @field_validator("inicio", "fim", mode="before")
    @classmethod
    def validar_datas(cls, valor: object) -> object:
        return exigir_data_iso(valor)

    @model_validator(mode="after")
    def exigir_inicio_ate_fim(self) -> "Janela":
        if self.inicio > self.fim:
            raise ValueError("inicio deve ser anterior ou igual a fim")
        return self


class JanelaDoLink(Janela):
    short_code: str = Field(min_length=1)


class JanelaDoCliente(Janela):
    cliente_id: str = Field(min_length=1)
