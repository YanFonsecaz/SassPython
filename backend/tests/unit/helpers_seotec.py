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
) -> bytes:
    buf = io.BytesIO()
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
            corpo = json.dumps(
                {"linhas": linhas, "total_antes_corte": len(linhas)}, ensure_ascii=False
            ).encode("utf-8")
            digest = hashlib.sha256(corpo).hexdigest()
            if nome == corromper_hash:
                digest = "0" * 64
            manifest["exports"][nome] = {"linhas": len(linhas), "hash": f"sha256:{digest}"}
            z.writestr(f"exports/{nome}.json", corpo)
        if not sem_manifest:
            z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
    return buf.getvalue()
