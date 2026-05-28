import pytest

from app.agents.cwv.pesquisador import (
    CWVPesquisadorAgent,
    FRAMEWORKS_SUPORTADOS_CTX7,
    SYSTEM,
)


def test_frameworks_supostados_includes_common():
    for fw in ("nextjs", "react", "vue", "shopify", "tailwind", "astro"):
        assert fw in FRAMEWORKS_SUPORTADOS_CTX7


def test_pesquisador_agent_init_no_tools_without_keys(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "api_context7_key", "")
    agent = CWVPesquisadorAgent(usuario_id="test-user", plataforma="shopify")
    assert len(agent._tools) == 2
    tool_names = {t.name for t in agent._tools}
    assert "buscar_web" in tool_names
    assert "fetch_url" in tool_names
    assert "buscar_docs_lib" not in tool_names


def test_pesquisador_agent_init_with_ctx7_for_framework(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "api_context7_key", "fake-ctx7-key")
    agent = CWVPesquisadorAgent(usuario_id="test-user", plataforma="nextjs")
    assert len(agent._tools) == 3
    tool_names = {t.name for t in agent._tools}
    assert "buscar_docs_lib" in tool_names


def test_pesquisador_agent_init_no_ctx7_for_non_framework(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "api_context7_key", "fake-ctx7-key")
    agent = CWVPesquisadorAgent(usuario_id="test-user", plataforma="vtex")
    assert len(agent._tools) == 2
    tool_names = {t.name for t in agent._tools}
    assert "buscar_docs_lib" not in tool_names


def test_pesquisador_agent_llm_has_tools_bound(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "api_context7_key", "")
    agent = CWVPesquisadorAgent(usuario_id="test-user", plataforma="wordpress")
    assert len(agent.llm.kwargs.get("tools", [])) == 2


def test_system_prompt_has_plataforma_placeholder():
    assert "{PLATAFORMA}" in SYSTEM
    assert "buscar_web" in SYSTEM
    assert "fetch_url" in SYSTEM
    assert "buscar_docs_lib" in SYSTEM


def test_pesquisador_agent_documentar_handles_exception(monkeypatch):
    agent = CWVPesquisadorAgent(usuario_id="test-user", plataforma="wordpress")

    async def fake_invoke(*args, **kwargs):
        raise RuntimeError("LLM error")

    monkeypatch.setattr(agent, "invoke_with_tools", fake_invoke)

    audit = {
        "id": "test-audit",
        "title": "Test Audit",
        "description": "Test description",
        "displayValue": "1.5s",
    }

    import asyncio
    result = asyncio.get_event_loop().run_until_complete(
        agent.documentar(audit=audit, plataforma="wordpress")
    )
    assert result is None


def test_pesquisador_uses_dedicated_llm_model(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "cwv_pesquisador_llm_model", "gpt-4.1")
    monkeypatch.setattr(settings, "cwv_pesquisador_llm_temperature", 0.4)
    monkeypatch.setattr(settings, "api_context7_key", "")
    monkeypatch.setattr(settings, "openai_api_key", "fake-key")

    agent = CWVPesquisadorAgent(usuario_id="test-user", plataforma="shopify")
    assert agent.llm.model_name == "gpt-4.1"
    assert agent.llm.temperature == 0.4
    assert len(agent.llm.kwargs.get("tools", [])) == 2


def test_pesquisador_config_defaults():
    from app.config import settings

    assert settings.cwv_pesquisador_llm_model == "gpt-4.1"
    assert settings.cwv_pesquisador_llm_temperature == 0.4


def test_pesquisador_no_override_when_not_openai(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "llm_provider", "zhipuai")
    monkeypatch.setattr(settings, "cwv_pesquisador_llm_model", "gpt-4.1")
    monkeypatch.setattr(settings, "api_context7_key", "")

    agent = CWVPesquisadorAgent(usuario_id="test-user", plataforma="shopify")
    assert agent.llm.model_name != "gpt-4.1"
