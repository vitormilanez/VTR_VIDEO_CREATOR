#!/usr/bin/env python3
"""
AI VIDEO CREATOR - Trend Hunter

Coleta tendências de notícias e, opcionalmente, Google Trends via SerpAPI
para gerar pautas de Reels sobre obesidade, emagrecimento, GLP-1 e saúde
metabólica.
"""

from __future__ import annotations

import csv
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import quote_plus

import feedparser
import requests
from dateutil import parser as date_parser

sys.path.append(str(Path(__file__).resolve().parents[1]))
from integrations.portuguese_br import apply_portuguese_br_accents


OUTPUT_DIR = Path(__file__).resolve().parent / "output"
TODAY = datetime.now().date().isoformat()

PERIODS = {
    "dia": "when:1d",
    "semana": "when:7d",
    "quinzena": "when:15d",
    "mes": "when:30d",
}

SEARCH_QUERIES = [
    "GLP-1 obesidade emagrecimento",
    "Mounjaro emagrecimento obesidade",
    "Ozempic emagrecimento obesidade",
    "Wegovy obesidade",
    "semaglutida emagrecimento",
    "tirzepatida emagrecimento",
    "dieta metabolismo obesidade",
    "saúde metabólica emagrecimento",
    "efeito sanfona obesidade",
    "resistência insulínica emagrecimento",
]

KEYWORDS = {
    "glp-1": 18,
    "glp": 12,
    "mounjaro": 18,
    "ozempic": 18,
    "wegovy": 16,
    "semaglutida": 16,
    "tirzepatida": 16,
    "obesidade": 12,
    "emagrecimento": 12,
    "perda de peso": 12,
    "dieta": 8,
    "metabolismo": 8,
    "saude metabolica": 10,
    "saúde metabólica": 10,
    "resistencia insulinica": 10,
    "resistência insulínica": 10,
    "diabetes": 8,
    "efeito sanfona": 8,
    "apetite": 6,
    "saciedade": 6,
}

SOURCE_WEIGHT = {
    "Google News RSS": 12,
    "SerpAPI Google Trends": 18,
}


@dataclass
class TrendItem:
    periodo: str
    fonte: str
    trend: str
    score: int
    termos_encontrados: str
    angulo_de_conteudo: str
    cuidado_medico_compliance: str
    link_da_fonte: str
    publicado_em: str


def normalize_text(value: str) -> str:
    value = value.lower()
    value = apply_portuguese_br_accents(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def google_news_rss_url(query: str, period_filter: str) -> str:
    full_query = f"{query} {period_filter}"
    return (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(full_query)}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    )


def extract_date(entry: dict) -> str:
    published = entry.get("published") or entry.get("updated")
    if not published:
        return ""
    try:
        return date_parser.parse(published).date().isoformat()
    except (TypeError, ValueError):
        return ""


def found_terms(text: str) -> list[str]:
    normalized = normalize_text(text)
    return [term for term in KEYWORDS if term in normalized]


def score_item(text: str, source: str, period: str, term_hits: Iterable[str]) -> int:
    score = SOURCE_WEIGHT.get(source, 0)
    score += sum(KEYWORDS[term] for term in term_hits)

    if period == "dia":
        score += 12
    elif period == "semana":
        score += 8
    elif period == "quinzena":
        score += 4

    normalized = normalize_text(text)
    if any(word in normalized for word in ["novo", "alerta", "estudo", "pesquisa", "aprov"]):
        score += 8
    if any(word in normalized for word in ["risco", "efeito colateral", "segurança"]):
        score += 6

    return score


def content_angle(title: str, terms: list[str]) -> str:
    normalized = normalize_text(title)

    if any(term in normalized for term in ["mounjaro", "ozempic", "wegovy", "semaglutida", "tirzepatida", "glp"]):
        return "Explicar o que a notícia muda na conversa sobre GLP-1 sem transformar em prescrição."
    if any(term in normalized for term in ["risco", "efeito colateral", "segurança"]):
        return "Fazer um Reel de alerta equilibrado: risco real, contexto médico e quando procurar acompanhamento."
    if any(term in normalized for term in ["dieta", "metabolismo", "saciedade", "apetite"]):
        return "Traduzir o mecanismo em linguagem simples e conectar com comportamento alimentar no dia a dia."
    if "obesidade" in terms:
        return "Reposicionar obesidade como doença crônica e reduzir culpa sem prometer solução fácil."
    return "Transformar a tendência em gancho educativo com explicação simples e CTA para avaliação individual."


def compliance_note(title: str) -> str:
    normalized = normalize_text(title)
    notes = [
        "Não prescrever medicamento, não citar dose e não prometer resultado.",
        "Validar informação médica com o Dr. Guilherme antes de publicar.",
    ]
    if any(term in normalized for term in ["mounjaro", "ozempic", "wegovy", "semaglutida", "tirzepatida", "glp"]):
        notes.append("Reforçar que medicação exige indicação, acompanhamento e avaliação individual.")
    if any(term in normalized for term in ["risco", "efeito colateral", "segurança"]):
        notes.append("Evitar sensacionalismo; diferenciar risco absoluto, perfil do paciente e contexto clínico.")
    return apply_portuguese_br_accents(" ".join(notes))


def fetch_google_news() -> list[TrendItem]:
    items: list[TrendItem] = []

    for period, period_filter in PERIODS.items():
        for query in SEARCH_QUERIES:
            url = google_news_rss_url(query, period_filter)
            feed = feedparser.parse(url)

            for entry in feed.entries[:8]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                summary = entry.get("summary", "")
                text = f"{title} {summary}"
                terms = found_terms(text)

                if not title or not terms:
                    continue

                score = score_item(text, "Google News RSS", period, terms)
                items.append(
                    TrendItem(
                        periodo=period,
                        fonte="Google News RSS",
                        trend=title,
                        score=score,
                        termos_encontrados=", ".join(terms),
                        angulo_de_conteudo=content_angle(title, terms),
                        cuidado_medico_compliance=compliance_note(title),
                        link_da_fonte=link,
                        publicado_em=extract_date(entry),
                    )
                )

    return items


def fetch_serpapi_trends() -> list[TrendItem]:
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        return []

    items: list[TrendItem] = []
    endpoint = "https://serpapi.com/search.json"

    for query in SEARCH_QUERIES:
        params = {
            "engine": "google_trends",
            "q": query,
            "geo": "BR",
            "date": "now 7-d",
            "api_key": api_key,
        }
        response = requests.get(endpoint, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()

        related = data.get("related_queries", {})
        rising = related.get("rising", []) if isinstance(related, dict) else []
        for row in rising[:10]:
            trend = row.get("query") or row.get("title") or query
            terms = found_terms(f"{query} {trend}")
            if not terms:
                terms = found_terms(query)
            score = score_item(f"{query} {trend}", "SerpAPI Google Trends", "semana", terms)
            value = row.get("value") or row.get("extracted_value")
            if isinstance(value, int):
                score += min(value // 100, 20)

            items.append(
                TrendItem(
                    periodo="semana",
                    fonte="SerpAPI Google Trends",
                    trend=trend,
                    score=score,
                    termos_encontrados=", ".join(terms),
                    angulo_de_conteudo=content_angle(trend, terms),
                    cuidado_medico_compliance=compliance_note(trend),
                    link_da_fonte="https://trends.google.com/trends/",
                    publicado_em=TODAY,
                )
            )

    return items


def dedupe_and_rank(items: list[TrendItem]) -> list[TrendItem]:
    best_by_key: dict[str, TrendItem] = {}

    for item in items:
        key = normalize_text(re.sub(r"\s+-\s+.*$", "", item.trend))
        current = best_by_key.get(key)
        if current is None or item.score > current.score:
            best_by_key[key] = item

    return sorted(best_by_key.values(), key=lambda item: item.score, reverse=True)


def write_csv(items: list[TrendItem], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(asdict(items[0]).keys()))
        writer.writeheader()
        for item in items:
            writer.writerow(asdict(item))


def write_json(items: list[TrendItem], path: Path) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump([asdict(item) for item in items], file, ensure_ascii=False, indent=2)


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Coletando tendencias no Google News RSS...")
    items = fetch_google_news()

    if os.getenv("SERPAPI_KEY"):
        print("SERPAPI_KEY encontrada. Coletando Google Trends via SerpAPI...")
        items.extend(fetch_serpapi_trends())
    else:
        print("SERPAPI_KEY nao encontrada. Pulando Google Trends opcional.")

    ranked = dedupe_and_rank(items)
    if not ranked:
        print("Nenhuma tendencia encontrada. Tente novamente mais tarde ou ajuste os termos.")
        return 1

    csv_path = OUTPUT_DIR / f"trends_{TODAY}.csv"
    json_path = OUTPUT_DIR / f"trends_{TODAY}.json"

    write_csv(ranked, csv_path)
    write_json(ranked, json_path)

    print(f"Gerado: {csv_path}")
    print(f"Gerado: {json_path}")
    print(f"Total de tendencias: {len(ranked)}")
    print("\nTop 5:")
    for item in ranked[:5]:
        print(f"- [{item.score}] {item.trend}")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.RequestException as exc:
        print(f"Erro de rede/API: {exc}", file=sys.stderr)
        raise SystemExit(2)
