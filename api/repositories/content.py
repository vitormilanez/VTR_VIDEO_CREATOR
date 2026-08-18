from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from api.database.models import (
    CalendarPost,
    Idea,
    LegacyIdMap,
    LegacyImportRun,
    PerformanceMetric,
    Script,
    Trend,
)
from api.database.session import Database


class ContentNotFoundError(LookupError):
    pass


class ContentConflictError(RuntimeError):
    pass


PRIORITY_TO_DB = {"alta": "high", "media": "medium", "baixa": "low"}
PRIORITY_FROM_DB = {value: key for key, value in PRIORITY_TO_DB.items()}
RISK_TO_DB = {"alto": "high", "medio": "medium", "baixo": "low"}
RISK_FROM_DB = {value: key for key, value in RISK_TO_DB.items()}
TREND_STATUS_TO_DB = {"novo": "new", "em_analise": "analyzing", "descartado": "discarded"}
TREND_STATUS_FROM_DB = {value: key for key, value in TREND_STATUS_TO_DB.items()}
IDEA_STATUS_TO_DB = {
    "novo": "new",
    "em_analise": "analyzing",
    "aprovado": "approved",
    "descartado": "discarded",
}
IDEA_STATUS_FROM_DB = {value: key for key, value in IDEA_STATUS_TO_DB.items()}
SCRIPT_STATUS_TO_DB = {
    "aguardando_validacao": "awaiting_validation",
    "em_revisao": "in_review",
    "aprovado_clinicamente": "clinically_approved",
    "rejeitado": "rejected",
}
SCRIPT_STATUS_FROM_DB = {value: key for key, value in SCRIPT_STATUS_TO_DB.items()}
POST_STATUS_TO_DB = {"pendente": "pending", "agendado": "scheduled", "publicado": "published"}
POST_STATUS_FROM_DB = {value: key for key, value in POST_STATUS_TO_DB.items()}


def _aware_datetime(value: Any, *, fallback: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    else:
        raw = str(value or "").strip()
        parsed = None
        if raw:
            normalized = f"{raw[:-1]}+00:00" if raw.endswith("Z") else raw
            try:
                parsed = datetime.fromisoformat(normalized)
            except ValueError:
                for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
                    try:
                        parsed = datetime.strptime(raw, fmt)
                        break
                    except ValueError:
                        continue
        if parsed is None:
            parsed = fallback or datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _optional_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    return _aware_datetime(value)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _family(*values: Any) -> str:
    blob = " ".join(str(value or "").casefold() for value in values)
    if any(word in blob for word in ("mounjaro", "ozempic", "wegovy", "glp", "medicament")):
        return "medicamento"
    if any(word in blob for word in ("metabol", "insulin", "resistenc")):
        return "metabolismo"
    if any(word in blob for word in ("obesidad", "estigma", "peso")):
        return "obesidade"
    if any(word in blob for word in ("jejum", "habito", "hábito", "comportament", "compuls", "sono", "dieta")):
        return "comportamento"
    return "educativo"


def _public_id(entity: Any, prefix: str) -> str:
    legacy_id = str(getattr(entity, "legacy_id", "") or "").strip()
    return legacy_id or f"{prefix}-{entity.id.hex[:12]}"


def _fingerprint(payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


class PostgresContentRepository:
    """Persistência tenant-aware para o conteúdo que antes vivia nas Sheets."""

    def __init__(self, database: Database, organization_id: uuid.UUID):
        self.database = database
        self.organization_id = organization_id

    def health(self) -> dict[str, Any]:
        with self.database.session() as session:
            session.execute(text("SELECT 1"))
            counts = {
                "trends": self._count(session, Trend),
                "ideas": self._count(session, Idea),
                "scripts": self._count(session, Script),
                "calendarPosts": self._count(session, CalendarPost),
                "performance": self._count(session, PerformanceMetric),
            }
        return {
            "ok": True,
            "backend": "postgres",
            "organizationId": str(self.organization_id),
            "counts": counts,
        }

    def _count(self, session: Session, model: type[Any]) -> int:
        statement = select(func.count()).select_from(model).where(model.organization_id == self.organization_id)
        if hasattr(model, "archived_at"):
            statement = statement.where(model.archived_at.is_(None))
        return int(session.scalar(statement) or 0)

    def state(self) -> dict[str, list[dict[str, Any]]]:
        with self.database.session() as session:
            trends = list(
                session.scalars(
                    select(Trend)
                    .where(Trend.organization_id == self.organization_id, Trend.archived_at.is_(None))
                    .order_by(Trend.created_at.desc(), Trend.id)
                )
            )
            ideas = list(
                session.scalars(
                    select(Idea)
                    .where(Idea.organization_id == self.organization_id, Idea.archived_at.is_(None))
                    .order_by(Idea.created_at.desc(), Idea.id)
                )
            )
            scripts = list(
                session.scalars(
                    select(Script)
                    .where(Script.organization_id == self.organization_id, Script.archived_at.is_(None))
                    .order_by(Script.created_at.desc(), Script.id)
                )
            )
            posts = list(
                session.scalars(
                    select(CalendarPost)
                    .where(CalendarPost.organization_id == self.organization_id)
                    .order_by(CalendarPost.scheduled_at.desc(), CalendarPost.id)
                )
            )
            metrics = list(
                session.scalars(
                    select(PerformanceMetric)
                    .where(PerformanceMetric.organization_id == self.organization_id)
                    .order_by(PerformanceMetric.observed_at.desc(), PerformanceMetric.id)
                )
            )

        trend_ids = {item.id: _public_id(item, "t") for item in trends}
        idea_ids = {item.id: _public_id(item, "i") for item in ideas}
        script_ids = {item.id: _public_id(item, "s") for item in scripts}
        post_ids = {item.id: _public_id(item, "p") for item in posts}
        post_by_id = {item.id: item for item in posts}
        return {
            "trends": [self._trend_dict(item) for item in trends],
            "ideas": [self._idea_dict(item, trend_ids) for item in ideas],
            "scripts": [self._script_dict(item, idea_ids) for item in scripts],
            "calendarPosts": [self._calendar_dict(item, script_ids) for item in posts],
            "performance": [
                self._performance_dict(item, post_ids, post_by_id, script_ids) for item in metrics
            ],
        }

    def get_script(self, public_id: str) -> dict[str, Any]:
        with self.database.session() as session:
            entity = self._by_public_id(session, Script, public_id, include_archived=False)
            if entity is None:
                raise ContentNotFoundError("Roteiro não encontrado no PostgreSQL.")
            idea_ids = self._legacy_id_map(session, Idea)
            return self._script_dict(entity, idea_ids)

    def list_calendar_posts(self) -> list[dict[str, Any]]:
        return self.state()["calendarPosts"]

    def create_trend(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.database.transaction() as session:
            entity, _ = self._upsert_trend(session, payload)
            session.flush()
            return self._trend_dict(entity)

    def create_idea(self, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        with self.database.transaction() as session:
            entity, created = self._upsert_idea(session, payload)
            session.flush()
            return self._idea_dict(entity, self._legacy_id_map(session, Trend)), not created

    def update_idea(self, public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = {**payload, "id": payload.get("id") or public_id}
        with self.database.transaction() as session:
            existing = self._by_public_id(session, Idea, public_id, include_archived=False)
            if existing is None:
                raise ContentNotFoundError("Ideia não encontrada no PostgreSQL.")
            entity, _ = self._upsert_idea(session, normalized, existing=existing)
            session.flush()
            return self._idea_dict(entity, self._legacy_id_map(session, Trend))

    def create_script(self, payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        with self.database.transaction() as session:
            entity, created = self._upsert_script(session, payload)
            session.flush()
            return self._script_dict(entity, self._legacy_id_map(session, Idea)), not created

    def update_script(self, public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = {**payload, "id": payload.get("id") or public_id}
        with self.database.transaction() as session:
            existing = self._by_public_id(session, Script, public_id, include_archived=False)
            if existing is None:
                raise ContentNotFoundError("Roteiro não encontrado no PostgreSQL.")
            entity, _ = self._upsert_script(session, normalized, existing=existing)
            session.flush()
            return self._script_dict(entity, self._legacy_id_map(session, Idea))

    def delete_script(self, public_id: str) -> dict[str, Any]:
        with self.database.transaction() as session:
            entity = self._by_public_id(session, Script, public_id, include_archived=False)
            if entity is None:
                raise ContentNotFoundError("Roteiro não encontrado no PostgreSQL.")
            linked = int(
                session.scalar(
                    select(func.count())
                    .select_from(CalendarPost)
                    .where(
                        CalendarPost.organization_id == self.organization_id,
                        CalendarPost.script_id == entity.id,
                    )
                )
                or 0
            )
            if linked:
                raise ContentConflictError(
                    "Este roteiro está ligado ao Calendário. Remova ou altere o agendamento antes de excluir."
                )
            entity.archived_at = datetime.now(timezone.utc)
            return {"id": public_id, "title": entity.title}

    def create_calendar_post(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self.database.transaction() as session:
            entity, _ = self._upsert_calendar_post(session, payload)
            session.flush()
            return self._calendar_dict(entity, self._legacy_id_map(session, Script))

    def update_calendar_post(self, public_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = {**payload, "id": payload.get("id") or public_id}
        with self.database.transaction() as session:
            existing = self._by_public_id(session, CalendarPost, public_id)
            if existing is None:
                raise ContentNotFoundError("Agendamento não encontrado no PostgreSQL.")
            entity, _ = self._upsert_calendar_post(session, normalized, existing=existing)
            session.flush()
            return self._calendar_dict(entity, self._legacy_id_map(session, Script))

    def set_status(self, resource: str, public_id: str, status: str) -> dict[str, Any]:
        config: dict[str, tuple[type[Any], dict[str, str]]] = {
            "radar": (Trend, TREND_STATUS_TO_DB),
            "ideias": (Idea, IDEA_STATUS_TO_DB),
            "roteiros": (Script, SCRIPT_STATUS_TO_DB),
            "calendario": (CalendarPost, POST_STATUS_TO_DB),
        }
        if resource not in config or status not in config[resource][1]:
            raise ValueError(f"Status inválido para {resource}: {status}")
        model, status_map = config[resource]
        with self.database.transaction() as session:
            entity = self._by_public_id(session, model, public_id, include_archived=False)
            if entity is None:
                raise ContentNotFoundError(f"Item {public_id} não encontrado no PostgreSQL.")
            entity.status = status_map[status]
        return {"ok": True, "status": status}

    def import_legacy_state(
        self,
        state: dict[str, list[dict[str, Any]]],
        *,
        source: str = "sheets_snapshot",
    ) -> dict[str, Any]:
        run_id = uuid.uuid4()
        counts: dict[str, dict[str, int]] = {}
        warnings: list[str] = []
        try:
            with self.database.transaction() as session:
                run = LegacyImportRun(
                    id=run_id,
                    organization_id=self.organization_id,
                    source=source,
                    status="running",
                    summary={},
                )
                session.add(run)
                session.flush()

                trend_aliases: dict[str, uuid.UUID] = {}
                for payload in state.get("trends", []):
                    entity, created = self._upsert_trend(session, payload)
                    self._count_result(counts, "trends", created)
                    self._record_legacy_map(session, run, "trend", payload, entity)
                    session.flush()
                    trend_aliases[str(payload.get("id") or "")] = entity.id
                    for alias in payload.get("legacyAliases") or []:
                        trend_aliases[str(alias)] = entity.id

                idea_aliases: dict[str, uuid.UUID] = {}
                for payload in state.get("ideas", []):
                    relation = str(payload.get("trendId") or "")
                    entity, created = self._upsert_idea(
                        session,
                        payload,
                        relation_id=trend_aliases.get(relation),
                    )
                    if relation and entity.trend_id is None:
                        warnings.append(f"Ideia {payload.get('id')} sem tendência resolvida: {relation}")
                    self._count_result(counts, "ideas", created)
                    self._record_legacy_map(session, run, "idea", payload, entity)
                    session.flush()
                    idea_aliases[str(payload.get("id") or "")] = entity.id

                script_aliases: dict[str, uuid.UUID] = {}
                for payload in state.get("scripts", []):
                    relation = str(payload.get("ideaId") or "")
                    entity, created = self._upsert_script(
                        session,
                        payload,
                        relation_id=idea_aliases.get(relation),
                    )
                    if relation and entity.idea_id is None:
                        warnings.append(f"Roteiro {payload.get('id')} sem ideia resolvida: {relation}")
                    self._count_result(counts, "scripts", created)
                    self._record_legacy_map(session, run, "script", payload, entity)
                    session.flush()
                    script_aliases[str(payload.get("id") or "")] = entity.id

                post_aliases: dict[str, uuid.UUID] = {}
                for payload in state.get("calendarPosts", []):
                    relation = str(payload.get("scriptId") or "")
                    entity, created = self._upsert_calendar_post(
                        session,
                        payload,
                        relation_id=script_aliases.get(relation),
                    )
                    if relation and entity.script_id is None:
                        warnings.append(f"Post {payload.get('id')} sem roteiro resolvido: {relation}")
                    self._count_result(counts, "calendarPosts", created)
                    self._record_legacy_map(session, run, "calendar_post", payload, entity)
                    session.flush()
                    post_aliases[str(payload.get("id") or "")] = entity.id

                for payload in state.get("performance", []):
                    relation = str(payload.get("calendarPostId") or payload.get("postId") or "")
                    relation_id = post_aliases.get(relation)
                    if relation_id is None:
                        warnings.append(f"Métrica {payload.get('id')} sem post resolvido: {relation or 'ausente'}")
                        continue
                    _, created = self._upsert_performance(session, payload, relation_id=relation_id)
                    self._count_result(counts, "performance", created)
                    session.flush()

                run.status = "succeeded"
                run.completed_at = datetime.now(timezone.utc)
                run.summary = {"counts": counts, "warnings": warnings}
        except Exception as exc:
            with self.database.transaction() as session:
                session.add(
                    LegacyImportRun(
                        id=run_id,
                        organization_id=self.organization_id,
                        source=source,
                        status="failed",
                        completed_at=datetime.now(timezone.utc),
                        summary={"counts": counts, "warnings": warnings},
                        error=str(exc),
                    )
                )
            raise

        return {
            "ok": True,
            "runId": str(run_id),
            "organizationId": str(self.organization_id),
            "counts": counts,
            "warnings": warnings,
        }

    @staticmethod
    def _count_result(counts: dict[str, dict[str, int]], key: str, created: bool) -> None:
        bucket = counts.setdefault(key, {"created": 0, "updated": 0})
        bucket["created" if created else "updated"] += 1

    def _record_legacy_map(
        self,
        session: Session,
        run: LegacyImportRun,
        entity_type: str,
        payload: dict[str, Any],
        entity: Any,
    ) -> None:
        if entity.id is None:
            session.flush()
        source_key = str(payload.get("sourceKey") or payload.get("id") or "").strip()
        if not source_key:
            return
        existing = session.scalar(
            select(LegacyIdMap).where(
                LegacyIdMap.organization_id == self.organization_id,
                LegacyIdMap.source_system == run.source,
                LegacyIdMap.entity_type == entity_type,
                LegacyIdMap.source_key == source_key,
            )
        )
        fingerprint = _fingerprint(payload)
        if existing is None:
            session.add(
                LegacyIdMap(
                    organization_id=self.organization_id,
                    import_run_id=run.id,
                    source_system=run.source,
                    entity_type=entity_type,
                    source_key=source_key,
                    target_table=entity.__tablename__,
                    target_id=entity.id,
                    fingerprint=fingerprint,
                )
            )
        else:
            existing.target_id = entity.id
            existing.target_table = entity.__tablename__
            existing.fingerprint = fingerprint

    def _legacy_id_map(self, session: Session, model: type[Any]) -> dict[uuid.UUID, str]:
        return {
            entity.id: _public_id(entity, {Trend: "t", Idea: "i", Script: "s", CalendarPost: "p"}[model])
            for entity in session.scalars(
                select(model).where(model.organization_id == self.organization_id)
            )
        }

    def _by_public_id(
        self,
        session: Session,
        model: type[Any],
        public_id: str,
        *,
        include_archived: bool = True,
    ) -> Any | None:
        conditions = [model.organization_id == self.organization_id]
        try:
            internal_id = uuid.UUID(str(public_id))
        except ValueError:
            conditions.append(model.legacy_id == str(public_id))
        else:
            conditions.append((model.id == internal_id) | (model.legacy_id == str(public_id)))
        statement = select(model).where(*conditions)
        if not include_archived and hasattr(model, "archived_at"):
            statement = statement.where(model.archived_at.is_(None))
        return session.scalar(statement)

    def _upsert_trend(
        self,
        session: Session,
        payload: dict[str, Any],
        *,
        existing: Trend | None = None,
    ) -> tuple[Trend, bool]:
        public_id = str(payload.get("id") or f"t-{uuid.uuid4().hex[:12]}")
        entity = existing or self._by_public_id(session, Trend, public_id)
        created = entity is None
        if entity is None:
            entity = Trend(organization_id=self.organization_id, legacy_id=public_id, title="")
            session.add(entity)
        created_at = _aware_datetime(payload.get("criadoEm"), fallback=datetime.now(timezone.utc))
        entity.legacy_id = public_id
        entity.trend_date = created_at.date()
        entity.title = str(payload.get("titulo") or "Tendência")
        entity.subtheme = payload.get("subtema") or None
        entity.source = payload.get("fonte") or "Importação legada"
        entity.reference_url = payload.get("link") or None
        entity.trend_signal = payload.get("sinal") or None
        entity.audience_pain = payload.get("dorPublico") or None
        entity.viral_potential = max(0, min(int(payload.get("potencial") or 0), 10))
        entity.priority = PRIORITY_TO_DB.get(str(payload.get("prioridade")), "medium")
        entity.status = TREND_STATUS_TO_DB.get(str(payload.get("status")), "new")
        entity.notes = payload.get("notas") or None
        entity.archived_at = None
        if created:
            entity.created_at = created_at
        return entity, created

    def _upsert_idea(
        self,
        session: Session,
        payload: dict[str, Any],
        *,
        existing: Idea | None = None,
        relation_id: uuid.UUID | None = None,
    ) -> tuple[Idea, bool]:
        public_id = str(payload.get("id") or f"i-{uuid.uuid4().hex[:12]}")
        entity = existing or self._by_public_id(session, Idea, public_id)
        if entity is None and not payload.get("id"):
            entity = session.scalar(
                select(Idea).where(
                    Idea.organization_id == self.organization_id,
                    func.lower(Idea.title) == str(payload.get("titulo") or "").strip().lower(),
                    Idea.hook == str(payload.get("hook") or ""),
                    Idea.origin_url == (payload.get("linkOrigem") or None),
                )
            )
        created = entity is None
        if entity is None:
            entity = Idea(organization_id=self.organization_id, legacy_id=public_id, title="")
            session.add(entity)
        if relation_id is None and payload.get("trendId"):
            related = self._by_public_id(session, Trend, str(payload["trendId"]), include_archived=False)
            relation_id = related.id if related else None
        entity.legacy_id = public_id
        entity.trend_id = relation_id
        entity.title = str(payload.get("titulo") or "Ideia")
        entity.family = str(payload.get("familia") or _family(payload.get("titulo"), payload.get("tipo")))
        entity.hook = str(payload.get("hook") or "")
        entity.angle = str(payload.get("angulo") or "")
        entity.content_type = payload.get("tipo") or None
        entity.audience_pain = payload.get("publicoDor") or None
        entity.cta = str(payload.get("cta") or "")
        entity.origin_url = payload.get("linkOrigem") or None
        entity.compliance_notes = str(payload.get("observacaoCompliance") or "")
        entity.priority = PRIORITY_TO_DB.get(str(payload.get("prioridade")), "medium")
        entity.status = IDEA_STATUS_TO_DB.get(str(payload.get("status")), "new")
        entity.archived_at = None
        if created:
            entity.created_at = _aware_datetime(payload.get("criadoEm"), fallback=datetime.now(timezone.utc))
        return entity, created

    def _upsert_script(
        self,
        session: Session,
        payload: dict[str, Any],
        *,
        existing: Script | None = None,
        relation_id: uuid.UUID | None = None,
    ) -> tuple[Script, bool]:
        public_id = str(payload.get("id") or f"s-{uuid.uuid4().hex[:12]}")
        entity = existing or self._by_public_id(session, Script, public_id)
        created = entity is None
        if entity is None:
            entity = Script(organization_id=self.organization_id, legacy_id=public_id, title="")
            session.add(entity)
        if relation_id is None and payload.get("ideaId"):
            related = self._by_public_id(session, Idea, str(payload["ideaId"]), include_archived=False)
            relation_id = related.id if related else None
        entity.legacy_id = public_id
        entity.idea_id = relation_id
        entity.category = str(payload.get("categoria") or "educativo")
        entity.theme = str(payload.get("tema") or "")
        entity.title = str(payload.get("titulo") or "Roteiro")
        entity.hook = str(payload.get("hook") or "")
        entity.conflict = str(payload.get("dorConflito") or "")
        entity.simple_explanation = str(payload.get("explicacaoSimples") or "")
        entity.turn = str(payload.get("virada") or "")
        entity.cta = str(payload.get("cta") or "")
        entity.medical_care = str(payload.get("cuidadosMedicos") or "")
        entity.risk = RISK_TO_DB.get(str(payload.get("risco")), "medium")
        entity.suggested_format = str(payload.get("formatoSugerido") or "Reels")
        entity.status = SCRIPT_STATUS_TO_DB.get(str(payload.get("status")), "awaiting_validation")
        entity.approver_name = payload.get("aprovador") or None
        entity.approved_at = _optional_datetime(payload.get("validadoEm"))
        entity.source_asset_url = payload.get("link") or None
        entity.editorial_tone = payload.get("editorialTone") or None
        entity.spoken_text = str(payload.get("textoFalado") or "")
        entity.outro_text = str(payload.get("outroText") or "")
        entity.generation_provider = payload.get("generationProvider") or None
        entity.generation_flow_version = payload.get("generationFlowVersion") or None
        entity.archived_at = None
        if created:
            entity.created_at = _aware_datetime(payload.get("criadoEm"), fallback=datetime.now(timezone.utc))
        return entity, created

    def _upsert_calendar_post(
        self,
        session: Session,
        payload: dict[str, Any],
        *,
        existing: CalendarPost | None = None,
        relation_id: uuid.UUID | None = None,
    ) -> tuple[CalendarPost, bool]:
        public_id = str(payload.get("id") or f"p-{uuid.uuid4().hex[:12]}")
        entity = existing or self._by_public_id(session, CalendarPost, public_id)
        created = entity is None
        if entity is None:
            entity = CalendarPost(
                organization_id=self.organization_id,
                legacy_id=public_id,
                title="",
                channel="instagram",
                scheduled_at=datetime.now(timezone.utc),
            )
            session.add(entity)
        if relation_id is None and payload.get("scriptId"):
            related = self._by_public_id(session, Script, str(payload["scriptId"]), include_archived=False)
            relation_id = related.id if related else None
        entity.legacy_id = public_id
        entity.script_id = relation_id
        entity.legacy_job_id = payload.get("videoJobId") or None
        entity.title = str(payload.get("titulo") or "Post")
        entity.theme = payload.get("tema") or None
        entity.content_format = payload.get("formato") or None
        entity.responsible = payload.get("responsavel") or None
        entity.channel = str(payload.get("canal") or "instagram")
        entity.status = POST_STATUS_TO_DB.get(str(payload.get("status")), "scheduled")
        entity.scheduled_at = _aware_datetime(payload.get("dataAgendada"))
        entity.published_at = _optional_datetime(payload.get("publicadoEm"))
        if entity.status == "published" and entity.published_at is None:
            entity.published_at = datetime.now(timezone.utc)
        entity.post_url = payload.get("link") or None
        return entity, created

    def _upsert_performance(
        self,
        session: Session,
        payload: dict[str, Any],
        *,
        relation_id: uuid.UUID,
    ) -> tuple[PerformanceMetric, bool]:
        observed_at = _aware_datetime(payload.get("coletadoEm"))
        entity = session.scalar(
            select(PerformanceMetric).where(
                PerformanceMetric.organization_id == self.organization_id,
                PerformanceMetric.calendar_post_id == relation_id,
                PerformanceMetric.observed_at == observed_at,
            )
        )
        created = entity is None
        if entity is None:
            entity = PerformanceMetric(
                organization_id=self.organization_id,
                calendar_post_id=relation_id,
                observed_at=observed_at,
            )
            session.add(entity)
        entity.views = max(0, int(payload.get("views") or 0))
        entity.likes = max(0, int(payload.get("likes") or 0))
        entity.retention_percent = Decimal(str(max(0, float(payload.get("retencao") or 0))))
        entity.comments = max(0, int(payload.get("comments") or 0))
        entity.shares = max(0, int(payload.get("shares") or 0))
        entity.saves = max(0, int(payload.get("saves") or 0))
        entity.new_followers = max(0, int(payload.get("novosSeguidores") or 0))
        entity.clicks = max(0, int(payload.get("cliques") or 0))
        entity.leads = max(0, int(payload.get("leads") or 0))
        entity.score_note = payload.get("nota") or None
        entity.learning = payload.get("aprendizado") or None
        entity.source_payload = dict(payload)
        return entity, created

    @staticmethod
    def _trend_dict(entity: Trend) -> dict[str, Any]:
        created = entity.created_at
        if entity.trend_date and (created is None or created.date() != entity.trend_date):
            created = datetime.combine(entity.trend_date, datetime.min.time(), tzinfo=timezone.utc)
        return {
            "id": _public_id(entity, "t"),
            "titulo": entity.title,
            "subtema": entity.subtheme,
            "sinal": entity.trend_signal,
            "dorPublico": entity.audience_pain,
            "link": entity.reference_url,
            "fonte": entity.source or "PostgreSQL",
            "potencial": entity.viral_potential,
            "volume": 0,
            "familia": _family(entity.title, entity.subtheme),
            "risco": "medio",
            "prioridade": PRIORITY_FROM_DB.get(entity.priority, "media"),
            "status": TREND_STATUS_FROM_DB.get(entity.status, "novo"),
            "criadoEm": _iso(created),
            "notas": entity.notes,
        }

    @staticmethod
    def _idea_dict(entity: Idea, trend_ids: dict[uuid.UUID, str]) -> dict[str, Any]:
        return {
            "id": _public_id(entity, "i"),
            "trendId": trend_ids.get(entity.trend_id) if entity.trend_id else None,
            "titulo": entity.title,
            "familia": entity.family,
            "hook": entity.hook,
            "angulo": entity.angle,
            "tipo": entity.content_type,
            "publicoDor": entity.audience_pain,
            "cta": entity.cta,
            "linkOrigem": entity.origin_url,
            "observacaoCompliance": entity.compliance_notes,
            "prioridade": PRIORITY_FROM_DB.get(entity.priority, "media"),
            "status": IDEA_STATUS_FROM_DB.get(entity.status, "novo"),
            "criadoEm": _iso(entity.created_at),
        }

    @staticmethod
    def _script_dict(entity: Script, idea_ids: dict[uuid.UUID, str]) -> dict[str, Any]:
        return {
            "id": _public_id(entity, "s"),
            "ideaId": idea_ids.get(entity.idea_id) if entity.idea_id else None,
            "categoria": entity.category,
            "tema": entity.theme,
            "titulo": entity.title,
            "hook": entity.hook,
            "dorConflito": entity.conflict,
            "explicacaoSimples": entity.simple_explanation,
            "virada": entity.turn,
            "cta": entity.cta,
            "cuidadosMedicos": entity.medical_care,
            "risco": RISK_FROM_DB.get(entity.risk, "medio"),
            "prioridade": "media",
            "formatoSugerido": entity.suggested_format,
            "aprovador": entity.approver_name,
            "link": entity.source_asset_url,
            "status": SCRIPT_STATUS_FROM_DB.get(entity.status, "aguardando_validacao"),
            "criadoEm": _iso(entity.created_at),
            "validadoEm": _iso(entity.approved_at),
            "editorialTone": entity.editorial_tone,
            "textoFalado": entity.spoken_text,
            "outroText": entity.outro_text,
            "generationProvider": entity.generation_provider,
            "generationFlowVersion": entity.generation_flow_version,
        }

    @staticmethod
    def _calendar_dict(entity: CalendarPost, script_ids: dict[uuid.UUID, str]) -> dict[str, Any]:
        return {
            "id": _public_id(entity, "p"),
            "scriptId": script_ids.get(entity.script_id) if entity.script_id else None,
            "videoJobId": entity.legacy_job_id,
            "titulo": entity.title,
            "dataAgendada": _iso(entity.scheduled_at),
            "canal": entity.channel,
            "status": POST_STATUS_FROM_DB.get(entity.status, "pendente"),
            "publicadoEm": _iso(entity.published_at),
            "tema": entity.theme,
            "formato": entity.content_format,
            "responsavel": entity.responsible,
            "link": entity.post_url,
        }

    @staticmethod
    def _performance_dict(
        entity: PerformanceMetric,
        post_ids: dict[uuid.UUID, str],
        posts: dict[uuid.UUID, CalendarPost],
        script_ids: dict[uuid.UUID, str],
    ) -> dict[str, Any]:
        post = posts.get(entity.calendar_post_id)
        source = entity.source_payload or {}
        return {
            "id": str(source.get("id") or f"m-{entity.id.hex[:12]}"),
            "postId": post_ids.get(entity.calendar_post_id, str(entity.calendar_post_id)),
            "tema": source.get("tema") or (post.theme if post else None),
            "canal": source.get("canal") or (post.channel if post else None),
            "views": entity.views,
            "likes": entity.likes,
            "retencao": float(entity.retention_percent),
            "comments": entity.comments,
            "shares": entity.shares,
            "saves": entity.saves,
            "novosSeguidores": entity.new_followers,
            "cliques": entity.clicks,
            "leads": entity.leads,
            "nota": entity.score_note,
            "aprendizado": entity.learning,
            "link": post.post_url if post else source.get("link"),
            "coletadoEm": _iso(entity.observed_at),
            "calendarPostId": post_ids.get(entity.calendar_post_id),
            "scriptId": script_ids.get(post.script_id) if post and post.script_id else None,
            "videoJobId": post.legacy_job_id if post else None,
            "formatoSugerido": post.content_format if post else None,
        }
