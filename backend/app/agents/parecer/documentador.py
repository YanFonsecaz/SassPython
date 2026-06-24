import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.parecer.modelos import get_modelo_redacao
from app.core.llm_guard import chamada_llm_mensagem_com_retry
from app.schemas.parecer import ParecerEstruturado

logger = logging.getLogger(__name__)

SYSTEM_DOC = (
    "Voce redige PARECERES TECNICOS de SEO/Performance no padrao de uma agencia, para enviar ao "
    "cliente aplicar as correcoes. Linguagem clara para nao-desenvolvedores, mas tecnicamente "
    "correta. Responda em portugues (pt-BR) com acentuacao correta.\n"
    "ESTRUTURA OBRIGATORIA (espelha o documento padrao):\n"
    "- Cabecalho: 'subtitulo' curto (ex.: 'Otimizacao de Core Web Vitals' ou o foco do parecer) e "
    "'escopo_linha' no formato '<metricas/foco> — <dominio se houver> (<Cliente>)'.\n"
    "- 'secoes': UMA por pagina/URL analisada. Cada secao tem 'titulo' (ex.: 'Pagina de produto — "
    "<nome>'), 'url' (se houver), 'observacao' opcional (ex.: 'Observacao: os problemas ocorrem de "
    "forma identica em Desktop e Mobile.') e 'subsecoes'.\n"
    "- Cada 'subsecao' tem 'titulo' (o tema; ex.: 'LCP atrasado por CSS bloqueante' ou 'Versao "
    "Desktop') e 1+ 'problemas'.\n"
    "- Cada 'problema' tem 'descricao' (o Problema), 'evidencias' (1+ itens, cada um com 'legenda' do "
    "que o print mostra), 'solucao' (acionavel; especifica para a PLATAFORMA quando possivel) e "
    "'solucao_escopo' opcional (ex.: 'Desktop e Mobile').\n"
    "- 'recomendacoes_globais': lista priorizada com 'titulo' ('Prioridade 1 — ...', 'Prioridade 2 "
    "— ...') e 'itens' em bullets.\n"
    "NAO inclua tabela de metadados nem sumario executivo. NAO invente URLs ou dados nao suportados "
    "pelas evidencias; se incerto, generalize. Vincule cada evidencia as imagens via "
    "'imagens_indices' (use os indices fornecidos). Se a entrada for um relato textual sem multiplas "
    "paginas, organize em 1 secao com subsecoes por problema."
)


async def gerar_parecer_estruturado(
    usuario_id: str,
    cliente_nome: str,
    blocos: list[dict],
    achados: list,
    titulo_sugerido: str = "",
) -> ParecerEstruturado:
    llm = get_modelo_redacao().with_structured_output(ParecerEstruturado, method="function_calling")

    blocos_texto = []
    for bloco in blocos:
        texto = bloco.get("texto", "").strip()
        if texto:
            blocos_texto.append(texto)

    achados_texto = []
    for a in achados:
        achados_texto.append(
            f"[Imagem {a.indice_global}] {a.o_que_mostra}\n"
            f"  Problema: {a.problema}\n"
            f"  Impacto: {', '.join(a.impacto)}\n"
            f"  Onde: {a.onde_ocorre}\n"
            f"  Confianca: {a.confianca:.0%}"
        )

    titulo_linha = (
        f"Titulo sugerido pelo usuario (use como base para o 'subtitulo'/foco do parecer): {titulo_sugerido}\n\n"
        if titulo_sugerido.strip()
        else ""
    )

    contexto = (
        f"Nome do cliente: {cliente_nome}\n\n"
        + titulo_linha
        + f"Notas do analista (blocos de texto):\n"
        + "\n---\n".join(blocos_texto)
        + "\n\nAnalise das imagens:\n"
        + "\n---\n".join(achados_texto)
    )

    msgs = [
        SystemMessage(content=SYSTEM_DOC),
        HumanMessage(content=contexto),
    ]
    resultado = await chamada_llm_mensagem_com_retry(llm, msgs, usuario_id)
    return resultado
