import base64
import io
import logging
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dependencies import get_current_user, get_db, rate_limit_autenticado
from app.models.cliente import Cliente
from app.models.execucao_ferramenta import ExecucaoFerramenta
from app.models.usuario import Usuario
from app.schemas.parecer import (
    CustoParecerResponse,
    ExportarParecerRequest,
    GerarParecerRequest,
    ParecerExecucaoResposta,
    ParecerHistoricoResponse,
    ParecerResposta,
)
from app.services import credito_service, ferramenta_service

logger = logging.getLogger(__name__)
router = APIRouter()

PAYLOAD_MAX_BYTES = 12 * 1024 * 1024
IMG_MAX_BYTES = 4 * 1024 * 1024
DATA_URI_RE = re.compile(r"^data:image/(png|jpe?g|gif|webp);base64,")


async def _validar_cliente(db: AsyncSession, usuario_id: str, cliente_id: str) -> Cliente:
    resultado = await db.execute(
        select(Cliente).where(Cliente.id == cliente_id, Cliente.usuario_id == usuario_id)
    )
    cliente = resultado.scalar_one_or_none()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente nao encontrado")
    return cliente


def _validar_blocos(blocos: list[dict]) -> tuple[int, int]:
    total_imagens = 0
    total_bytes = 0
    for b in blocos:
        for img_uri in b.get("imagens", []):
            if not DATA_URI_RE.match(img_uri):
                raise HTTPException(status_code=422, detail="Esquema de imagem invalido. Use data:image/(png|jpeg|gif|webp);base64,")
            b64_part = img_uri.split(",", 1)[1] if "," in img_uri else ""
            try:
                img_bytes = len(base64.b64decode(b64_part))
            except Exception:
                img_bytes = len(b64_part.encode())
            if img_bytes > IMG_MAX_BYTES:
                raise HTTPException(status_code=413, detail="Uma das imagens excede 4 MB. Reduza o tamanho.")
            total_bytes += img_bytes
            total_imagens += 1
        total_bytes += len(b.get("texto", "").encode())
    if total_imagens == 0:
        has_any_text = any(b.get("texto", "").strip() for b in blocos)
        if not has_any_text:
            raise HTTPException(status_code=422, detail="Envie pelo menos texto ou imagem.")
    return total_imagens, total_bytes


@router.post("/parecer/custo", response_model=CustoParecerResponse)
async def custo_parecer(
    body: GerarParecerRequest,
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    n = body.total_imagens
    return {
        "custo": ferramenta_service.calcular_custo_parecer(n),
        "custo_base": ferramenta_service.CUSTO_BASE_PARECER,
        "custo_por_imagem": ferramenta_service.CUSTO_POR_IMAGEM_PARECER,
        "n_imagens": n,
    }


@router.post("/parecer/gerar", status_code=202)
async def gerar_parecer(
    body: GerarParecerRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    _: None = Depends(rate_limit_autenticado("parecer_gerar", max_requests=5, window_seconds=300)),
) -> dict[str, Any]:
    cliente = await _validar_cliente(db, str(usuario.id), str(body.cliente_id))
    custo = ferramenta_service.calcular_custo_parecer(body.total_imagens)

    try:
        await credito_service.reservar_creditos(db, str(usuario.id), custo)
    except ValueError as exc:
        raise HTTPException(status_code=402, detail="Creditos insuficientes") from exc

    entrada = body.model_dump(mode="json")
    entrada["cliente_nome"] = cliente.nome

    try:
        n_imgs, total_bytes = _validar_blocos(entrada.get("blocos", []))
    except HTTPException:
        await credito_service.liberar_reserva(db, str(usuario.id), custo)
        raise
    if total_bytes > PAYLOAD_MAX_BYTES:
        await credito_service.liberar_reserva(db, str(usuario.id), custo)
        raise HTTPException(status_code=413, detail="Payload excede 12 MB. Reduza o numero ou tamanho das imagens.")

    execucao = ExecucaoFerramenta(
        usuario_id=str(usuario.id),
        cliente_id=str(body.cliente_id),
        ferramenta="parecer_tecnico",
        status="pendente",
        entrada_json=entrada,
        creditos_cobrados=custo,
        thread_id=str(uuid.uuid4()),
        timeout_em=datetime.now(UTC) + timedelta(seconds=settings.parecer_workflow_timeout),
    )
    db.add(execucao)
    await db.flush()
    await db.commit()

    try:
        from app.core.redis_pool import get_redis_pool
        redis = await get_redis_pool()
        job = await redis.enqueue_job("executar_workflow_parecer", str(execucao.id))
        execucao.job_id = job.job_id
        execucao.status = "enfileirado"
        db.add(execucao)
        await db.flush()
        await db.commit()
    except Exception as e:
        logger.error("Falha ao enfileirar parecer: %s", e)
        async with db.begin():
            await credito_service.liberar_reserva(db, str(usuario.id), custo)
            execucao.status = "falhou"
            execucao.erro_msg = "Falha ao enfileirar workflow"
            await db.flush()

    logger.info("parecer.gerar.enfileirado", extra={
        "event_type": "parecer.gerar.enfileirado",
        "execucao_id": str(execucao.id),
        "usuario_id": str(usuario.id),
        "n_imagens": n_imgs,
        "custo": custo,
    })
    return {"id": str(execucao.id), "status": execucao.status, "custo_estimado": custo}


@router.get("/parecer/execucao/{execucao_id}", response_model=ParecerExecucaoResposta)
async def buscar_execucao_parecer(
    execucao_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    resultado = await db.execute(
        select(ExecucaoFerramenta).where(
            ExecucaoFerramenta.id == execucao_id,
            ExecucaoFerramenta.usuario_id == usuario.id,
            ExecucaoFerramenta.ferramenta == "parecer_tecnico",
        )
    )
    ex = resultado.scalar_one_or_none()
    if not ex:
        raise HTTPException(status_code=404, detail="Execucao nao encontrada")
    resultado_json = ex.resultado_json or {}
    return {
        "id": str(ex.id),
        "ferramenta": ex.ferramenta,
        "status": ex.status,
        "etapa_atual": ex.etapa_atual,
        "creditos_cobrados": ex.creditos_cobrados,
        "parecer_id": resultado_json.get("parecer_id"),
        "erro_msg": ex.erro_msg,
        "criado_em": str(ex.criado_em),
        "concluida_em": str(ex.concluida_em) if ex.concluida_em else None,
    }


# IMPORTANTE: rota estatica "/parecer/historico" deve vir ANTES da dinamica "/parecer/{parecer_id}",
# senao "historico" e capturado como parecer_id.
@router.get("/parecer/historico", response_model=ParecerHistoricoResponse)
async def listar_historico_parecer(
    cliente_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    from app.services import parecer_persistencia
    pareceres = await parecer_persistencia.listar_pareceres(db, str(usuario.id), cliente_id=cliente_id)
    return {"pareceres": [parecer_persistencia.parecer_resumo_dict(p) for p in pareceres]}


@router.get("/parecer/{parecer_id}", response_model=ParecerResposta)
async def buscar_parecer(
    parecer_id: str,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
) -> dict[str, Any]:
    from app.services import parecer_persistencia
    p = await parecer_persistencia.buscar_parecer(db, parecer_id, str(usuario.id))
    if not p:
        raise HTTPException(status_code=404, detail="Parecer nao encontrado")
    return parecer_persistencia.parecer_to_dict(p)


@router.post("/parecer/{parecer_id}/exportar")
async def exportar_parecer(
    parecer_id: str,
    body: ExportarParecerRequest,
    db: AsyncSession = Depends(get_db),
    usuario: Usuario = Depends(get_current_user),
    _: None = Depends(rate_limit_autenticado("parecer_exportar", max_requests=20, window_seconds=300)),
) -> StreamingResponse:
    from app.services import parecer_persistencia

    p = await parecer_persistencia.buscar_parecer(db, parecer_id, str(usuario.id))
    if not p:
        raise HTTPException(status_code=404, detail="Parecer nao encontrado")

    await parecer_persistencia.atualizar_html(db, parecer_id, str(usuario.id), body.html)
    await db.commit()

    from app.services.parecer_service import html_para_docx_bytes
    docx_bytes = html_para_docx_bytes(body.html)

    logger.info("parecer.exportar", extra={
        "event_type": "parecer.exportar",
        "parecer_id": parecer_id,
        "bytes": len(docx_bytes),
    })

    nome = (body.nome_arquivo or "parecer-tecnico").rsplit(".", 1)[0]
    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{nome}.docx"'},
    )
