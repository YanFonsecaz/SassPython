from app.services.seotec_checklist import carregar_checklist, recarregar_checklist
from app.services.seotec_score import calcular_health_score


def _ck():
    recarregar_checklist()
    return carregar_checklist()


def test_todos_aprovados_score_100():
    ck = _ck()
    statuses = {i.slug: "aprovado" for i in ck.itens()}
    r = calcular_health_score(ck, statuses)
    assert r.score == 100.0
    assert r.pontos == 940
    assert r.total_pontos == 940


def test_na_pontua_como_aprovado():
    ck = _ck()
    statuses = {i.slug: "na" for i in ck.itens()}
    assert calcular_health_score(ck, statuses).score == 100.0


def test_nenhum_status_score_0():
    ck = _ck()
    assert calcular_health_score(ck, {}).score == 0.0


def test_reprovado_atencao_sem_dados_nao_pontuam():
    ck = _ck()
    statuses = {i.slug: "aprovado" for i in ck.itens()}
    statuses["title-tag-ausente-ou-vazia"] = "reprovado"   # peso 10
    statuses["title-duplicado"] = "atencao"                # peso 9
    statuses["conteudo-duplicado"] = "sem_dados"           # peso 10
    r = calcular_health_score(ck, statuses)
    assert r.pontos == 940 - 10 - 9 - 10
    assert r.score == round((940 - 29) / 940 * 100, 2)


def test_agregados():
    ck = _ck()
    statuses = {i.slug: "aprovado" for i in ck.itens()}
    statuses["title-tag-ausente-ou-vazia"] = "reprovado"
    r = calcular_health_score(ck, statuses)
    assert r.por_prioridade["very-high"]["reprovado"] == 1
    cat = r.por_categoria["Tag <title>"]
    assert cat["total_pontos"] == 41
    assert cat["pontos"] == 31
