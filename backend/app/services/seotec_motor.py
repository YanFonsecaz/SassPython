"""Motor de regras determinístico SEOTEC (SPEC_SEOTEC_Checklist_Motor_Regras §3.2).

Funções puras: (definição do item, pacote) -> ResultadoItem. Zero LLM, zero IO.
"""
import re
from collections import Counter

from pydantic import BaseModel, Field

from app.services.seotec_checklist import ItemChecklist, RegraFiltro
from app.services.seotec_ingestao import PacoteIngestao

MAX_AMOSTRA = 100


class ResultadoItem(BaseModel):
    status: str
    total_avaliadas: int = 0
    total_afetadas: int = 0
    amostra: list[dict] = Field(default_factory=list)
    truncada: bool = False


def _coagir_numero(valor: object) -> int | float | None:
    """Converte `valor` para número quando possível (int/float direto, ou str numérica).

    Usado pelos operadores maior/menor/entre para não perder defeitos reais só
    porque o export trouxe o campo como string (comum em CSVs do SF).
    """
    if isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return valor
    if isinstance(valor, str):
        try:
            return float(valor)
        except ValueError:
            return None
    return None


def _linha_casa(linha: dict, filtro: RegraFiltro) -> bool:
    valor = linha.get(filtro.campo)
    match filtro.op:
        case "vazio":
            return valor is None or (isinstance(valor, str) and not valor.strip())
        case "nao_vazio":
            return not _linha_casa(linha, RegraFiltro(campo=filtro.campo, op="vazio"))
        case "igual":
            return valor == filtro.valor or str(valor) == str(filtro.valor)
        case "regex":
            return valor is not None and re.search(str(filtro.valor), str(valor)) is not None
        case "maior":
            numero = _coagir_numero(valor)
            return numero is not None and numero > filtro.valor
        case "menor":
            numero = _coagir_numero(valor)
            return numero is not None and numero < filtro.valor
        case "entre":
            lo, hi = filtro.valor
            numero = _coagir_numero(valor)
            return numero is not None and lo <= numero <= hi
        case "len_maior":
            return valor is not None and len(str(valor)) > filtro.valor
        case "duplicado":
            return False  # tratado em _filtrar (precisa do conjunto)
    return False


def _filtrar(linhas: list[dict], filtro: RegraFiltro) -> list[dict]:
    if filtro.op == "duplicado":
        valores = Counter(
            str(li.get(filtro.campo)).strip()
            for li in linhas
            if li.get(filtro.campo) is not None and str(li.get(filtro.campo)).strip()
        )
        repetidos = {v for v, n in valores.items() if n > 1}
        return [li for li in linhas if str(li.get(filtro.campo)).strip() in repetidos]
    return [li for li in linhas if _linha_casa(li, filtro)]


def _montar_amostra(afetadas: list[dict], colunas: list[str]) -> list[dict]:
    corte = afetadas[:MAX_AMOSTRA]
    if not colunas:
        return corte
    return [{c: li.get(c) for c in colunas} for li in corte]


def avaliar_item(item: ItemChecklist, pacote: PacoteIngestao) -> ResultadoItem:
    regra = item.regra
    if regra is None:
        return ResultadoItem(status="sem_dados")
    export = pacote.exports.get(regra.export)
    if export is None:
        return ResultadoItem(status="sem_dados")

    linhas = export.linhas
    if not linhas and regra.na_se_export_vazio:
        return ResultadoItem(status="na", total_avaliadas=export.total_antes_corte)

    colunas = item.evidencia.colunas if item.evidencia else []

    if regra.tipo == "existencia":
        ok = any(li.get(regra.campo) for li in linhas)
        return ResultadoItem(
            status="aprovado" if ok else "reprovado",
            total_avaliadas=len(linhas),
            total_afetadas=0 if ok else len(linhas),
            amostra=[] if ok else _montar_amostra(linhas, colunas),
            truncada=False if ok else len(linhas) > MAX_AMOSTRA,
        )

    if regra.tipo == "custom":
        from app.services import seotec_motor_custom

        fn = getattr(seotec_motor_custom, regra.funcao)
        return fn(item, pacote)

    afetadas = _filtrar(linhas, regra.filtro)
    n = len(afetadas)
    if regra.tipo == "proporcao":
        proporcao = n / len(linhas) if linhas else 0.0
        limite = regra.limite_proporcao or 0.0
        status = "aprovado" if proporcao <= limite else "reprovado"
    elif n == 0:
        status = "aprovado"
    elif n <= regra.atencao_max:
        status = "atencao"
    else:
        status = "reprovado"

    return ResultadoItem(
        status=status,
        total_avaliadas=export.total_antes_corte or len(linhas),
        total_afetadas=n,
        amostra=_montar_amostra(afetadas, colunas),
        truncada=len(afetadas) > MAX_AMOSTRA,
    )
