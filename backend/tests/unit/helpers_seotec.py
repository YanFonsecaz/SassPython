"""Monta pacotes .zip do contrato de ingestão SEOTEC para testes."""
import hashlib
import io
import json
import zipfile


def montar_pacote_zip(
    exports: dict[str, list[dict]],
    schema_version: int = 1,
    corromper_hash: str | None = None,
    sem_manifest: bool = False,
    corpo_bruto: dict[str, bytes] | None = None,
    manifest_exports_override: object | None = None,
    meta_override: dict[str, object] | None = None,
) -> bytes:
    """Monta um pacote .zip de teste.

    `corpo_bruto`: substitui o corpo serializado de um export por bytes crus
    (para simular JSON válido mas não-objeto, ex.: `"str"`, `[]`, `42`, `null`).
    `manifest_exports_override`: substitui `manifest["exports"]` inteiro por
    qualquer valor (ex.: uma lista, para simular manifest malformado).
    `meta_override`: substitui a entrada de um export específico dentro de
    `manifest["exports"]` (ex.: por uma string, para simular meta inválida).
    """
    buf = io.BytesIO()
    corpo_bruto = corpo_bruto or {}
    meta_override = meta_override or {}
    manifest: dict = {
        "schema_version": schema_version,
        "conector_versao": "0.0.0-teste",
        "sf_versao": "24.1",
        "dominio": "https://exemplo.com.br",
        "gerado_em": "2026-07-18T12:00:00+00:00",
        "exports": {},
    }
    with zipfile.ZipFile(buf, "w") as z:
        for nome, linhas in exports.items():
            if nome in corpo_bruto:
                corpo = corpo_bruto[nome]
            else:
                corpo = json.dumps(
                    {"linhas": linhas, "total_antes_corte": len(linhas)}, ensure_ascii=False
                ).encode("utf-8")
            digest = hashlib.sha256(corpo).hexdigest()
            if nome == corromper_hash:
                digest = "0" * 64
            if nome in meta_override:
                manifest["exports"][nome] = meta_override[nome]
            else:
                manifest["exports"][nome] = {"linhas": len(linhas), "hash": f"sha256:{digest}"}
            z.writestr(f"exports/{nome}.json", corpo)
        if manifest_exports_override is not None:
            manifest["exports"] = manifest_exports_override
        if not sem_manifest:
            z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
    return buf.getvalue()
