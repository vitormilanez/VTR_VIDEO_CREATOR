from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from api.services.medical_identity import MEDICAL_DEFAULT_SAFE_CTA


def _norm(value: Any) -> str:
    return str(value or "").strip().casefold()


def _integer(value: Any) -> int:
    digits = re.sub(r"[^\d]", "", str(value or ""))
    return int(digits) if digits else 0


def _iso(value: Any) -> str:
    raw = str(value or "").strip()
    if raw:
        normalized = f"{raw[:-1]}+00:00" if raw.endswith("Z") else raw
        try:
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            pass
        for fmt in ("%d/%m/%Y", "%d/%m/%y"):
            try:
                return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc).isoformat()
            except ValueError:
                continue
    return datetime(1970, 1, 1, tzinfo=timezone.utc).isoformat()


def _optional_iso(value: Any) -> str | None:
    return _iso(value) if str(value or "").strip() else None


def _link(value: Any) -> str | None:
    raw = str(value or "").strip()
    return raw if raw.lower().startswith("http") else None


def _priority(value: Any) -> str:
    normalized = _norm(value)
    if "alt" in normalized:
        return "alta"
    if "baix" in normalized:
        return "baixa"
    return "media"


def _risk(value: Any) -> str:
    normalized = _norm(value)
    if "alt" in normalized:
        return "alto"
    if "baix" in normalized:
        return "baixo"
    return "medio"


def _family(*values: Any) -> str:
    blob = " ".join(_norm(value) for value in values)
    if any(word in blob for word in ("mounjaro", "ozempic", "wegovy", "glp", "medicament")):
        return "medicamento"
    if any(word in blob for word in ("metabol", "insulin", "resistenc")):
        return "metabolismo"
    if any(word in blob for word in ("obesidad", "estigma", "peso")):
        return "obesidade"
    if any(word in blob for word in ("jejum", "habito", "hábito", "comportament", "compuls", "sono", "dieta")):
        return "comportamento"
    return "educativo"


def _trend_status(value: Any) -> str:
    normalized = _norm(value)
    if "descart" in normalized or "rejeit" in normalized:
        return "descartado"
    if "anali" in normalized or "análi" in normalized or "andament" in normalized or "ideia" in normalized:
        return "em_analise"
    return "novo"


def _idea_status(value: Any) -> str:
    normalized = _norm(value)
    if "aprov" in normalized or "gerad" in normalized:
        return "aprovado"
    if "descart" in normalized or "rejeit" in normalized:
        return "descartado"
    if "anali" in normalized or "análi" in normalized:
        return "em_analise"
    return "novo"


def _script_status(value: Any) -> str:
    normalized = _norm(value)
    if "aprov" in normalized or "pronto" in normalized:
        return "aprovado_clinicamente"
    if "rejeit" in normalized or "arquiv" in normalized:
        return "rejeitado"
    if "revis" in normalized or "edi" in normalized:
        return "em_revisao"
    return "aguardando_validacao"


def _post_status(value: Any) -> str:
    normalized = _norm(value)
    if "public" in normalized:
        return "publicado"
    if "agend" in normalized:
        return "agendado"
    return "pendente"


def _channel(value: Any) -> str:
    normalized = _norm(value)
    if "tiktok" in normalized:
        return "tiktok"
    if "you" in normalized or "short" in normalized:
        return "youtube_shorts"
    return "instagram"


def _stable_trend_id(row: dict[str, Any], index: int) -> tuple[str, str]:
    existing = str(row.get("ID") or "").strip()
    source_material = "|".join(
        str(row.get(key) or "").strip()
        for key in ("Link referência", "Sinal de tendência", "Tema", "Data")
    )
    if not source_material.strip("|"):
        source_material = f"row:{index}"
    digest = hashlib.sha256(source_material.encode("utf-8")).hexdigest()
    return existing or f"t-{digest[:12]}", f"radar:{digest}"


def normalize_snapshot(snapshot: dict[str, Any]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    sheets = deepcopy(snapshot.get("sheets") or {})
    state: dict[str, list[dict[str, Any]]] = {
        "trends": [],
        "ideas": [],
        "scripts": [],
        "calendarPosts": [],
        "performance": [],
    }
    warnings: list[str] = []
    trend_aliases: dict[str, str] = {}

    for index, row in enumerate(sheets.get("radar") or []):
        public_id, source_key = _stable_trend_id(row, index)
        positional_alias = f"t-{index}"
        trend_aliases[positional_alias] = public_id
        trend_aliases[public_id] = public_id
        state["trends"].append(
            {
                "id": public_id,
                "sourceKey": source_key,
                "legacyAliases": [positional_alias] if positional_alias != public_id else [],
                "titulo": row.get("Tema") or row.get("Sinal de tendência") or "Tendência",
                "subtema": row.get("Subtema") or None,
                "sinal": row.get("Sinal de tendência") or None,
                "dorPublico": row.get("Dor do público") or None,
                "link": _link(row.get("Link referência")),
                "fonte": row.get("Fonte") or "Snapshot legado",
                "potencial": min(_integer(row.get("Potencial Viral")), 10),
                "volume": 0,
                "familia": _family(row.get("Tema"), row.get("Subtema")),
                "risco": "medio",
                "prioridade": _priority(row.get("Prioridade")),
                "status": _trend_status(row.get("Status")),
                "criadoEm": _iso(row.get("Data")),
                "notas": row.get("Observações") or None,
            }
        )

    for index, row in enumerate(sheets.get("ideias") or []):
        public_id = str(row.get("ID") or f"i-{index}").strip()
        raw_trend_id = str(row.get("Trend ID") or "").strip()
        trend_id = trend_aliases.get(raw_trend_id, raw_trend_id or None)
        if raw_trend_id and trend_id == raw_trend_id and raw_trend_id not in trend_aliases:
            warnings.append(f"Ideia {public_id} referencia tendência ausente: {raw_trend_id}")
        state["ideas"].append(
            {
                "id": public_id,
                "sourceKey": public_id,
                "trendId": trend_id,
                "titulo": row.get("Tema") or row.get("Hook") or "Ideia",
                "familia": _family(row.get("Tema"), row.get("Tipo")),
                "hook": row.get("Hook") or "",
                "angulo": row.get("Ângulo") or "",
                "tipo": row.get("Tipo") or None,
                "publicoDor": row.get("Público/Dor") or None,
                "cta": row.get("CTA") or "",
                "linkOrigem": _link(row.get("Link origem")),
                "observacaoCompliance": row.get("Observações") or "",
                "prioridade": _priority(row.get("Prioridade")),
                "status": _idea_status(row.get("Status")),
                "criadoEm": _iso(row.get("Criado em") or row.get("Data")),
            }
        )

    idea_ids = {str(item["id"]) for item in state["ideas"]}
    for index, row in enumerate(sheets.get("roteiros") or []):
        public_id = str(row.get("ID") or f"s-{index}").strip()
        idea_id = str(row.get("Idea ID") or "").strip() or None
        if idea_id and idea_id not in idea_ids:
            warnings.append(f"Roteiro {public_id} referencia ideia ausente: {idea_id}")
        state["scripts"].append(
            {
                "id": public_id,
                "sourceKey": public_id,
                "ideaId": idea_id,
                "categoria": _family(row.get("Categoria"), row.get("Tema")),
                "tema": row.get("Tema") or "",
                "titulo": row.get("Título") or row.get("Tema") or "Roteiro",
                "hook": row.get("Hook") or "",
                "dorConflito": row.get("Dor/Conflito") or "",
                "explicacaoSimples": row.get("Explicação simples") or "",
                "virada": row.get("Virada/Provocação") or "",
                "cta": row.get("CTA") or "",
                "cuidadosMedicos": row.get("Cuidados médicos") or "",
                "risco": _risk(row.get("Risco")),
                "prioridade": "media",
                "formatoSugerido": row.get("Formato sugerido") or "Reels",
                "aprovador": row.get("Aprovador") or None,
                "link": _link(row.get("Link doc/video")),
                "status": _script_status(row.get("Status")),
                "criadoEm": _iso(row.get("Criado em") or row.get("Data")),
                "validadoEm": _optional_iso(row.get("Data aprovação")),
                "editorialTone": row.get("Tom editorial") or None,
                "textoFalado": row.get("Texto falado") or "",
                "outroText": row.get("Frase final") or MEDICAL_DEFAULT_SAFE_CTA,
                "generationProvider": row.get("Gerado por") or None,
                "generationFlowVersion": row.get("Versão do fluxo") or None,
            }
        )

    script_ids = {str(item["id"]) for item in state["scripts"]}
    posts_by_link: dict[str, str] = {}
    for index, row in enumerate(sheets.get("calendario") or []):
        public_id = str(row.get("ID") or f"p-{index}").strip()
        script_id = str(row.get("Roteiro ID") or "").strip() or None
        if script_id and script_id not in script_ids:
            warnings.append(f"Post {public_id} referencia roteiro ausente: {script_id}")
        link = _link(row.get("Link post"))
        if link:
            posts_by_link[link] = public_id
        state["calendarPosts"].append(
            {
                "id": public_id,
                "sourceKey": public_id,
                "titulo": row.get("Título/Hook") or row.get("Tema") or "Post",
                "tema": row.get("Tema") or None,
                "formato": row.get("Formato") or None,
                "responsavel": row.get("Responsável") or None,
                "link": link,
                "dataAgendada": _iso(row.get("Data publicação")),
                "canal": _channel(row.get("Canal")),
                "status": _post_status(row.get("Status")),
                "scriptId": script_id,
                "videoJobId": row.get("Video Job ID") or None,
                "publicadoEm": _optional_iso(row.get("Publicado em")),
            }
        )

    for index, row in enumerate(sheets.get("performance") or []):
        link = _link(row.get("Link post"))
        state["performance"].append(
            {
                "id": str(row.get("ID") or f"m-{index}"),
                "postId": posts_by_link.get(link or "") or f"perf-{index}",
                "calendarPostId": posts_by_link.get(link or ""),
                "tema": row.get("Tema") or None,
                "canal": _channel(row.get("Canal")),
                "views": _integer(row.get("Views")),
                "likes": _integer(row.get("Likes")),
                "retencao": _integer(row.get("Retenção %")),
                "comments": _integer(row.get("Comentários")),
                "shares": _integer(row.get("Compartilhamentos")),
                "saves": _integer(row.get("Salvamentos")),
                "novosSeguidores": _integer(row.get("Novos seguidores")),
                "cliques": _integer(row.get("Cliques")),
                "leads": _integer(row.get("Leads")),
                "nota": row.get("Nota") or None,
                "aprendizado": row.get("Aprendizado") or None,
                "link": link,
                "coletadoEm": _iso(row.get("Data")),
            }
        )

    report = {
        "source": snapshot.get("source"),
        "updatedAt": snapshot.get("updated_at"),
        "counts": {key: len(value) for key, value in state.items()},
        "warnings": warnings,
    }
    return state, report


def load_and_normalize_snapshot(path: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return normalize_snapshot(payload)
