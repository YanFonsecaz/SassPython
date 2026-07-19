"""Validação do pacote de ingestão SEOTEC (SPEC_SEOTEC_Conector_Local_SF §3.3).

Pacote .zip: manifest.json + exports/<nome>.json. Cada export:
{"linhas": [{...}], "total_antes_corte": N}. Hash sha256 do corpo no manifest.
Export ausente/corrompido vira `faltante` (ingestão parcial), nunca erro fatal —
erro fatal é só manifest/zip/schema_version inválidos.
"""
import hashlib
import io
import json
import zipfile

from pydantic import BaseModel, Field

SCHEMA_VERSION = 1

EXPORTS_CONHECIDOS: set[str] = {
    "robots", "sitemaps", "response_codes", "internal", "page_titles",
    "meta_description", "h1", "images", "redirects",
    "directives", "pagina_404", "orfas", "sitemap_response_codes",
    "extracoes", "structured_data", "hreflang", "amp",
    "canonicals", "content", "security", "seguranca_site",
}

MAX_LINHAS_POR_EXPORT = 500

# Hardening contra zip bomb: limites sobre o tamanho DESCOMPRIMIDO (ZipInfo.file_size),
# nunca lido de fato acima do limite.
MAX_BYTES_POR_ENTRADA = 20 * 1024 * 1024
MAX_BYTES_DESCOMPRIMIDO_TOTAL = 100 * 1024 * 1024


class ExportNormalizado(BaseModel):
    linhas: list[dict] = Field(default_factory=list)
    total_antes_corte: int = 0


class PacoteIngestao(BaseModel):
    schema_version: int
    dominio: str
    sf_versao: str | None = None
    gerado_em: str | None = None
    exports: dict[str, ExportNormalizado] = Field(default_factory=dict)


class ResultadoValidacao(BaseModel):
    pacote: PacoteIngestao | None = None
    faltantes: list[str] = Field(default_factory=list)
    erros: list[str] = Field(default_factory=list)

    @property
    def parcial(self) -> bool:
        return self.pacote is not None and bool(self.faltantes)


def validar_pacote(zip_bytes: bytes, exports_requeridos: set[str]) -> ResultadoValidacao:
    r = ResultadoValidacao()
    try:
        z = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        r.erros.append("Arquivo não é um zip válido")
        return r

    try:
        manifest_info = z.getinfo("manifest.json")
    except KeyError:
        r.erros.append("manifest.json ausente no pacote")
        return r
    if manifest_info.file_size > MAX_BYTES_POR_ENTRADA:
        r.erros.append("manifest.json inválido: excede limite de tamanho")
        return r

    try:
        manifest = json.loads(z.read(manifest_info))
    except json.JSONDecodeError:
        r.erros.append("manifest.json inválido")
        return r

    versao = manifest.get("schema_version")
    if versao != SCHEMA_VERSION:
        r.erros.append(f"schema_version não suportada: {versao} (esperado {SCHEMA_VERSION})")
        return r

    pacote = PacoteIngestao(
        schema_version=versao,
        dominio=str(manifest.get("dominio") or ""),
        sf_versao=manifest.get("sf_versao"),
        gerado_em=manifest.get("gerado_em"),
    )

    declarados = manifest.get("exports") or {}
    if not isinstance(declarados, dict):
        r.erros.append("manifest.json inválido: campo 'exports' não é um objeto")
        return r

    def _marcar_faltante(nome: str) -> None:
        if nome in exports_requeridos:
            r.faltantes.append(nome)

    total_bytes_lidos = 0
    orcamento_estourado = False

    for nome, meta in declarados.items():
        if nome not in EXPORTS_CONHECIDOS:
            continue
        if not isinstance(meta, dict):
            r.erros.append(f"{nome}: entrada do manifest inválida")
            _marcar_faltante(nome)
            continue
        caminho = f"exports/{nome}.json"
        if orcamento_estourado:
            r.erros.append(f"{nome}: orçamento de descompressão do pacote excedido")
            _marcar_faltante(nome)
            continue
        try:
            info = z.getinfo(caminho)
        except KeyError:
            r.erros.append(f"{nome}: declarado no manifest mas ausente no zip")
            _marcar_faltante(nome)
            continue
        if info.file_size > MAX_BYTES_POR_ENTRADA:
            r.erros.append(f"{nome}: export excede limite de tamanho")
            _marcar_faltante(nome)
            continue
        total_bytes_lidos += info.file_size
        if total_bytes_lidos > MAX_BYTES_DESCOMPRIMIDO_TOTAL:
            r.erros.append(f"{nome}: orçamento de descompressão do pacote excedido")
            _marcar_faltante(nome)
            orcamento_estourado = True
            continue
        corpo = z.read(info)
        hash_declarado = str(meta.get("hash", "")).removeprefix("sha256:")
        if hashlib.sha256(corpo).hexdigest() != hash_declarado:
            r.erros.append(f"{nome}: hash não confere")
            _marcar_faltante(nome)
            continue
        try:
            dados = json.loads(corpo)
            if not isinstance(dados, dict):
                raise TypeError("corpo do export não é um objeto JSON")
            exp = ExportNormalizado(**dados)
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            r.erros.append(f"{nome}: JSON inválido ({exc})")
            _marcar_faltante(nome)
            continue
        exp.linhas = exp.linhas[:MAX_LINHAS_POR_EXPORT]
        pacote.exports[nome] = exp

    for nome in sorted(exports_requeridos):
        if nome not in pacote.exports and nome not in r.faltantes:
            r.faltantes.append(nome)

    r.pacote = pacote
    return r
