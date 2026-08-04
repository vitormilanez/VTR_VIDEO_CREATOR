#!/usr/bin/env python3
"""
AI VIDEO CREATOR - Trend Hunter

Coleta tendências de notícias e, opcionalmente, Google Trends via SerpAPI
para gerar pautas de Reels sobre obesidade, emagrecimento, GLP-1 e saúde
metabólica.
"""

from __future__ import annotations

import csv
import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from integrations.google_news import resolve_google_news_url


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


def normalize_keyword(value: str) -> str:
    return normalize_text(value).replace("saude", "saúde")


def build_keywords(custom_terms: list[str]) -> dict[str, int]:
    keywords = dict(KEYWORDS)
    for term in custom_terms:
        normalized = normalize_text(term)
        if len(normalized) < 3:
            continue
        keywords.setdefault(normalized, 12)
        keywords.setdefault(apply_portuguese_br_accents(normalized), 12)
    return keywords


def build_search_queries(custom_terms: list[str]) -> list[str]:
    if not custom_terms:
        return SEARCH_QUERIES
    queries: list[str] = []
    seen: set[str] = set()
    for term in custom_terms:
        cleaned = re.sub(r"\s+", " ", term).strip()
        if len(cleaned) < 3:
            continue
        candidates = [cleaned]
        if not any(word in normalize_text(cleaned) for word in ["obesidade", "emagrec", "metabol", "glp"]):
            candidates = [f"{cleaned} saúde obesidade"]
        for query in candidates:
            key = normalize_text(query)
            if key in seen:
                continue
            seen.add(key)
            queries.append(query)
    return (queries or SEARCH_QUERIES)[:20]


def parallel_collect(tasks: list[tuple], worker, max_workers: int = 8) -> list[TrendItem]:
    """Executa consultas independentes sem deixar uma fonte lenta travar todo o radar."""
    if not tasks:
        return []
    items: list[TrendItem] = []
    with ThreadPoolExecutor(max_workers=min(max_workers, len(tasks))) as executor:
        futures = [executor.submit(worker, *task) for task in tasks]
        for future in as_completed(futures):
            try:
                items.extend(future.result())
            except Exception:
                continue
    return items

SOURCE_WEIGHT = {
    "Google News RSS": 12,
    "SerpAPI Google Trends": 18,
    "GDELT": 14,
    "PubMed": 16,
    "Reddit": 10,
}


@dataclass
class TrendItem:
    periodo: str
    fonte: str
    tipo: str
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


def period_days(period: str) -> int:
    return {"dia": 1, "semana": 7, "quinzena": 15, "mes": 30}.get(period, 7)


def extract_date(entry: dict) -> str:
    published = entry.get("published") or entry.get("updated")
    if not published:
        return ""
    try:
        return date_parser.parse(published).date().isoformat()
    except (TypeError, ValueError):
        return ""


def found_terms(text: str, keywords: dict[str, int]) -> list[str]:
    normalized = normalize_text(text)
    return [term for term in keywords if term in normalized]


def score_item(
    text: str,
    source: str,
    period: str,
    term_hits: Iterable[str],
    keywords: dict[str, int],
) -> int:
    score = SOURCE_WEIGHT.get(source, 0)
    score += sum(keywords[term] for term in term_hits)

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


def fetch_google_news(
    *,
    queries: list[str],
    periods: list[str],
    keywords: dict[str, int],
    per_query: int,
) -> list[TrendItem]:
    def fetch_one(period: str, query: str) -> list[TrendItem]:
        items: list[TrendItem] = []
        period_filter = PERIODS[period]
        try:
            response = requests.get(google_news_rss_url(query, period_filter), timeout=(5, 12))
            response.raise_for_status()
            feed = feedparser.parse(response.content)
        except requests.RequestException:
            return []
        for entry in feed.entries[:per_query]:
            title = entry.get("title", "").strip()
            link = resolve_google_news_url(entry.get("link", "").strip())
            summary = entry.get("summary", "")
            text = f"{title} {summary}"
            terms = found_terms(text, keywords)
            if not title or not terms:
                continue
            score = score_item(text, "Google News RSS", period, terms, keywords)
            items.append(
                TrendItem(
                    periodo=period,
                    fonte="Google News RSS",
                    tipo="Notícia",
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

    return parallel_collect([(period, query) for period in periods for query in queries], fetch_one)


def fetch_gdelt(
    *,
    queries: list[str],
    period: str,
    keywords: dict[str, int],
    per_query: int,
) -> list[TrendItem]:
    endpoint = "https://api.gdeltproject.org/api/v2/doc/doc"
    timespan = f"{period_days(period)}d"

    def fetch_one(query: str) -> list[TrendItem]:
        items: list[TrendItem] = []
        params = {
            "query": query,
            "mode": "ArtList",
            "format": "json",
            "maxrecords": max(3, min(per_query, 15)),
            "sort": "HybridRel",
            "timespan": timespan,
        }
        try:
            response = requests.get(endpoint, params=params, timeout=(5, 12))
            response.raise_for_status()
            data = response.json()
        except (requests.RequestException, ValueError):
            return []

        for article in data.get("articles", [])[:per_query]:
            title = str(article.get("title") or "").strip()
            url = str(article.get("url") or "").strip()
            domain = str(article.get("domain") or "GDELT")
            text = f"{title} {article.get('seendate') or ''} {domain}"
            terms = found_terms(f"{query} {text}", keywords)
            if not title or not terms:
                continue
            score = score_item(text, "GDELT", period, terms, keywords)
            items.append(
                TrendItem(
                    periodo=period,
                    fonte=f"GDELT · {domain}",
                    tipo="Notícia global",
                    trend=title,
                    score=score,
                    termos_encontrados=", ".join(terms),
                    angulo_de_conteudo=content_angle(title, terms),
                    cuidado_medico_compliance=compliance_note(title),
                    link_da_fonte=url,
                    publicado_em=parse_gdelt_date(str(article.get("seendate") or "")),
                )
            )
        return items

    return parallel_collect([(query,) for query in queries], fetch_one)


def parse_gdelt_date(value: str) -> str:
    if not value:
        return ""
    try:
        return date_parser.parse(value).date().isoformat()
    except (TypeError, ValueError):
        return ""


def fetch_pubmed(
    *,
    queries: list[str],
    period: str,
    keywords: dict[str, int],
    per_query: int,
) -> list[TrendItem]:
    search_endpoint = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    summary_endpoint = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
    days = period_days(period)

    def fetch_one(query: str) -> list[TrendItem]:
        items: list[TrendItem] = []
        params = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "sort": "pub date",
            "retmax": max(3, min(per_query, 10)),
            "reldate": days,
            "datetype": "pdat",
        }
        try:
            response = requests.get(search_endpoint, params=params, timeout=(5, 12))
            response.raise_for_status()
            ids = response.json().get("esearchresult", {}).get("idlist", [])
        except (requests.RequestException, ValueError):
            return []
        if not ids:
            return []
        try:
            summary_response = requests.get(
                summary_endpoint,
                params={"db": "pubmed", "id": ",".join(ids), "retmode": "json"},
                timeout=(5, 12),
            )
            summary_response.raise_for_status()
            result = summary_response.json().get("result", {})
        except (requests.RequestException, ValueError):
            return []
        for pubmed_id in ids:
            row = result.get(pubmed_id) or {}
            title = str(row.get("title") or "").strip().rstrip(".")
            terms = found_terms(f"{query} {title}", keywords)
            if not title or not terms:
                continue
            score = score_item(title, "PubMed", period, terms, keywords) + 6
            items.append(
                TrendItem(
                    periodo=period,
                    fonte="PubMed",
                    tipo="Estudo científico",
                    trend=title,
                    score=score,
                    termos_encontrados=", ".join(terms),
                    angulo_de_conteudo="Traduzir o achado científico em linguagem simples, sem extrapolar causalidade nem prometer resultado.",
                    cuidado_medico_compliance=compliance_note(title),
                    link_da_fonte=f"https://pubmed.ncbi.nlm.nih.gov/{pubmed_id}/",
                    publicado_em=str(row.get("pubdate") or ""),
                )
            )
        return items

    return parallel_collect([(query,) for query in queries], fetch_one)


def fetch_reddit(
    *,
    queries: list[str],
    period: str,
    keywords: dict[str, int],
    per_query: int,
) -> list[TrendItem]:
    endpoint = "https://www.reddit.com/search.json"
    reddit_period = {"dia": "day", "semana": "week", "quinzena": "month", "mes": "month"}.get(
        period,
        "week",
    )
    headers = {"User-Agent": "VTRVideoCreatorTrendHunter/1.0"}
    def fetch_one(query: str) -> list[TrendItem]:
        items: list[TrendItem] = []
        params = {
            "q": query,
            "sort": "hot",
            "t": reddit_period,
            "limit": max(3, min(per_query, 10)),
        }
        try:
            response = requests.get(endpoint, params=params, headers=headers, timeout=(5, 12))
            response.raise_for_status()
            children = response.json().get("data", {}).get("children", [])
        except (requests.RequestException, ValueError):
            return []
        for child in children:
            data = child.get("data") or {}
            title = str(data.get("title") or "").strip()
            subreddit = str(data.get("subreddit_name_prefixed") or "Reddit")
            terms = found_terms(f"{query} {title}", keywords)
            if not title or not terms:
                continue
            comments = int(data.get("num_comments") or 0)
            ups = int(data.get("ups") or 0)
            score = score_item(title, "Reddit", period, terms, keywords)
            score += min(comments // 5, 12) + min(ups // 50, 10)
            permalink = str(data.get("permalink") or "")
            items.append(
                TrendItem(
                    periodo=period,
                    fonte=f"Reddit · {subreddit}",
                    tipo="Dúvida do público",
                    trend=title,
                    score=score,
                    termos_encontrados=", ".join(terms),
                    angulo_de_conteudo="Usar como sinal de dor real do público; transformar em explicação educativa sem responder como consulta individual.",
                    cuidado_medico_compliance=compliance_note(title),
                    link_da_fonte=f"https://www.reddit.com{permalink}" if permalink else "https://www.reddit.com/search/",
                    publicado_em=datetime.fromtimestamp(
                        float(data.get("created_utc") or 0),
                        tz=timezone.utc,
                    ).date().isoformat()
                    if data.get("created_utc")
                    else TODAY,
                )
            )
        return items

    return parallel_collect([(query,) for query in queries], fetch_one)


def fetch_serpapi_trends(*, queries: list[str], keywords: dict[str, int]) -> list[TrendItem]:
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        return []

    items: list[TrendItem] = []
    endpoint = "https://serpapi.com/search.json"

    for query in queries:
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
            terms = found_terms(f"{query} {trend}", keywords)
            if not terms:
                terms = found_terms(query, keywords)
            score = score_item(
                f"{query} {trend}",
                "SerpAPI Google Trends",
                "semana",
                terms,
                keywords,
            )
            value = row.get("value") or row.get("extracted_value")
            if isinstance(value, int):
                score += min(value // 100, 20)

            items.append(
                TrendItem(
                    periodo="semana",
                    fonte="SerpAPI Google Trends",
                    tipo="Busca em alta",
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Busca tendencias para o AI Video Creator.")
    parser.add_argument(
        "--query",
        action="append",
        default=[],
        help="Termo prioritario. Pode ser usado varias vezes.",
    )
    parser.add_argument(
        "--period",
        choices=list(PERIODS),
        default="semana",
        help="Janela principal da busca.",
    )
    parser.add_argument(
        "--per-query",
        type=int,
        default=8,
        help="Itens lidos por consulta no Google News.",
    )
    parser.add_argument(
        "--source",
        action="append",
        choices=["google_news", "gdelt", "pubmed", "reddit", "serpapi"],
        default=[],
        help="Fonte de busca. Pode repetir. Padrao: google_news, gdelt, pubmed, reddit e serpapi quando houver chave.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    custom_terms = [term.strip() for term in args.query if term.strip()]
    queries = build_search_queries(custom_terms)
    keywords = build_keywords(custom_terms)
    sources = set(args.source or ["google_news", "gdelt", "pubmed", "reddit", "serpapi"])
    periods = [args.period]
    if args.period != "dia":
        periods.insert(0, "dia")

    print("Coletando tendencias...")
    print(f"Fontes ativas: {', '.join(sorted(sources))}")
    print(f"Consultas ativas: {len(queries)}")
    for query in queries[:12]:
        print(f"- {query}")
    if len(queries) > 12:
        print(f"... +{len(queries) - 12} consultas")
    per_query = max(3, min(args.per_query, 15))
    items: list[TrendItem] = []
    if "google_news" in sources:
        items.extend(
            fetch_google_news(
                queries=queries,
                periods=periods,
                keywords=keywords,
                per_query=per_query,
            )
        )
    if "gdelt" in sources:
        items.extend(fetch_gdelt(queries=queries, period=args.period, keywords=keywords, per_query=per_query))
    if "pubmed" in sources:
        items.extend(fetch_pubmed(queries=queries, period=args.period, keywords=keywords, per_query=per_query))
    if "reddit" in sources:
        items.extend(fetch_reddit(queries=queries, period=args.period, keywords=keywords, per_query=per_query))

    if "serpapi" in sources and os.getenv("SERPAPI_KEY"):
        print("SERPAPI_KEY encontrada. Coletando Google Trends via SerpAPI...")
        items.extend(fetch_serpapi_trends(queries=queries, keywords=keywords))
    elif "serpapi" in sources:
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
