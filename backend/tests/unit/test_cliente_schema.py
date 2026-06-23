"""Testes do schema de cliente — focados em validar normalizacao de URL e personas.

Identifica bugs do fluxo "criar persona + salvar cliente" relatado.
"""
import pytest
from pydantic import ValidationError

from app.schemas.cliente import (
    ClienteCreateRequest,
    ClienteUpdateRequest,
    ConfigJsonSchema,
    PersonaGlobalSchema,
    PersonaSchema,
    normalizar_site_url,
)


# --------------------------------------------------------------------------- #
# normalizar_site_url
# --------------------------------------------------------------------------- #
class TestNormalizarSiteUrl:
    def test_none_retorna_none(self):
        assert normalizar_site_url(None) is None

    def test_string_vazia_retorna_none(self):
        assert normalizar_site_url("") is None
        assert normalizar_site_url("   ") is None

    def test_sem_protocolo_adiciona_https(self):
        assert normalizar_site_url("exemplo.com.br") == "https://exemplo.com.br/"

    def test_http_preservado(self):
        assert normalizar_site_url("http://exemplo.com.br") == "http://exemplo.com.br/"

    def test_https_preservado(self):
        assert normalizar_site_url("https://exemplo.com.br") == "https://exemplo.com.br/"

    def test_sem_barra_final_adiciona(self):
        assert normalizar_site_url("https://exemplo.com.br") == "https://exemplo.com.br/"

    def test_com_barra_final_preserva(self):
        assert normalizar_site_url("https://exemplo.com.br/") == "https://exemplo.com.br/"

    def test_com_espacos_faz_strip(self):
        assert normalizar_site_url("  exemplo.com.br  ") == "https://exemplo.com.br/"

    def test_com_path_preserva_path(self):
        assert normalizar_site_url("https://exemplo.com.br/blog") == "https://exemplo.com.br/blog/"


# --------------------------------------------------------------------------- #
# ClienteCreateRequest - site_url
# --------------------------------------------------------------------------- #
class TestClienteCreateSiteUrl:
    def test_url_completa_valida(self):
        req = ClienteCreateRequest(nome="Clinica Teste", site_url="https://exemplo.com.br/")
        assert req.site_url == "https://exemplo.com.br/"

    def test_url_sem_protocolo_aceita_e_normaliza(self):
        """Bug do ticket: usuario digita so o dominio e recebia 422."""
        req = ClienteCreateRequest(nome="Clinica Teste", site_url="exemplo.com.br")
        assert req.site_url == "https://exemplo.com.br/"

    def test_url_none_aceita(self):
        req = ClienteCreateRequest(nome="Clinica Teste", site_url=None)
        assert req.site_url is None

    def test_url_vazia_aceita_como_none(self):
        req = ClienteCreateRequest(nome="Clinica Teste", site_url="")
        assert req.site_url is None

    def test_url_invalida_ainda_rejeita(self):
        """'https://xyz' sem dominio deve rejeitar — nao e normalizacao burra."""
        with pytest.raises(ValidationError) as exc:
            ClienteCreateRequest(nome="Clinica Teste", site_url="https://xyz")
        assert "dominio" in str(exc.value).lower()

    def test_url_apenas_protocolo_rejeita(self):
        with pytest.raises(ValidationError):
            ClienteCreateRequest(nome="Clinica Teste", site_url="https://")

    def test_nome_curto_rejeita(self):
        with pytest.raises(ValidationError):
            ClienteCreateRequest(nome="A")  # min_length=2


# --------------------------------------------------------------------------- #
# ClienteCreateRequest - personas (cenario do ticket)
# --------------------------------------------------------------------------- #
class TestClienteCreatePersonas:
    def test_criar_com_persona_funciona(self):
        """Cenario exato do ticket: criar persona e salvar cliente."""
        persona = PersonaSchema(nome="Gestor de Clinica")
        req = ClienteCreateRequest(
            nome="Clinica OdontoVida",
            site_url="https://odontovida.com.br/",
            config_json=ConfigJsonSchema(personas=[persona]),
        )
        assert len(req.config_json.personas) == 1
        assert req.config_json.personas[0].nome == "Gestor de Clinica"

    def test_personas_com_nomes_duplicados_rejeita(self):
        """Validador anti-duplicidade ainda funciona (case-insensitive)."""
        p1 = PersonaSchema(nome="Gestor")
        p2 = PersonaSchema(nome="gestor")  # mesmo nome, case diferente
        with pytest.raises(ValidationError) as exc:
            ClienteCreateRequest(
                nome="Clinica",
                config_json=ConfigJsonSchema(personas=[p1, p2]),
            )
        assert "unicos" in str(exc.value).lower()

    def test_persona_sem_campos_opcionais_funciona(self):
        """So nome e obrigatorio; defaults devem preencher o resto."""
        p = PersonaSchema(nome="X")
        assert p.tom_voz == "profissional"
        assert p.nivel_tecnico == "intermediario"
        assert p.palavras_proibidas == []

    def test_config_padrao_tem_persona_global(self):
        req = ClienteCreateRequest(nome="Clinica")
        assert isinstance(req.config_json.persona_global, PersonaGlobalSchema)
        assert req.config_json.persona_global.tom_voz == "profissional"

    def test_persona_com_muitas_palavras_proibidas_rejeita(self):
        with pytest.raises(ValidationError):
            PersonaSchema(nome="X", palavras_proibidas=["w"] * 51)


# --------------------------------------------------------------------------- #
# ClienteUpdateRequest
# --------------------------------------------------------------------------- #
class TestClienteUpdate:
    def test_tudo_none_aceita(self):
        req = ClienteUpdateRequest()
        assert req.nome is None
        assert req.site_url is None

    def test_url_normalizada_no_update(self):
        req = ClienteUpdateRequest(site_url="exemplo.com.br")
        assert req.site_url == "https://exemplo.com.br/"

    def test_url_vazia_vira_none(self):
        """Importante: PUT com site_url='' nao deve 422."""
        req = ClienteUpdateRequest(site_url="")
        assert req.site_url is None
