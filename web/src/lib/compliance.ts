// Utilitario de compliance mockado.
// Localiza palavras proibidas e emite alertas medicos comuns.

export interface ComplianceHit {
  palavra: string;
  count: number;
  campo?: string;
}

export interface ComplianceAlert {
  id: string;
  titulo: string;
  detalhe: string;
  severidade: "alta" | "media" | "baixa";
}

/**
 * Formato das regras vindas de GET /api/state (complianceRules), a mesma
 * lista que o backend usa para bloquear producao no HeyGen (_pack_compliance
 * em api/server.py). Passar essa lista aqui evita que o preview do frontend
 * fique com regras diferentes do bloqueio real.
 */
export interface ComplianceRule {
  id: string;
  pattern: string;
  titulo: string;
  detalhe: string;
  severidade: "alta" | "media" | "baixa";
}

const medicalPatterns: Array<{
  id: string;
  regex: RegExp;
  titulo: string;
  detalhe: string;
  severidade: ComplianceAlert["severidade"];
}> = [
  {
    id: "dose",
    regex: /\b\d+(?:[.,]\d+)?\s?(mg|mcg|ml|g)\b/i,
    titulo: "Possivel mencao de dose especifica",
    detalhe:
      "Evitar orientacao de dose numerica individual. Nomes de medicamentos e apresentacoes podem ser explicados de forma educativa.",
    severidade: "alta",
  },
  {
    id: "promessa",
    regex: /\b(cura|milagre|garant\w+|resultado certo|prometo|emagrec\w+\s+rapid)/i,
    titulo: "Linguagem de promessa",
    detalhe: "Nao prometer resultado. Substituir por linguagem educativa e individualizada.",
    severidade: "alta",
  },
  {
    id: "prescrever",
    regex: /\bprescrev\w+|\breceit\w+/i,
    titulo: "Termo de prescricao",
    detalhe: "Nao prescrever pelo video. Reforcar consulta individual.",
    severidade: "alta",
  },
  {
    id: "sensacional",
    regex: /\b(chocante|inacreditavel|voce nao vai acreditar|surreal|absurdo)\b/i,
    titulo: "Tom sensacionalista",
    detalhe: "Evitar sensacionalismo. Manter tom educativo.",
    severidade: "media",
  },
  {
    id: "autodx",
    regex: /\b(voce (esta|tem)\s+(diabetes|resistencia|obesidade))/i,
    titulo: "Sugestao de autodiagnostico",
    detalhe: "Nao induzir autodiagnostico. Reforcar avaliacao clinica.",
    severidade: "media",
  },
];

const defaultRules: ComplianceRule[] = medicalPatterns.map((p) => ({
  id: p.id,
  pattern: p.regex.source,
  titulo: p.titulo,
  detalhe: p.detalhe,
  severidade: p.severidade,
}));

export function scanCompliance(
  fields: Record<string, string>,
  palavrasProibidas: string[],
  rules: ComplianceRule[] = defaultRules,
): { hits: ComplianceHit[]; alertas: ComplianceAlert[]; ok: boolean } {
  const hitMap = new Map<string, ComplianceHit>();
  const alertMap = new Map<string, ComplianceAlert>();
  const activeRules = rules.length ? rules : defaultRules;
  const compiledRules = activeRules.map((rule) => ({
    ...rule,
    regex: new RegExp(rule.pattern, "i"),
  }));

  const forbidden = palavrasProibidas
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => ({
      palavra: p,
      regex: new RegExp(`\\b${p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\b`, "gi"),
    }));

  for (const [campo, text] of Object.entries(fields)) {
    if (!text) continue;
    for (const f of forbidden) {
      const m = text.match(f.regex);
      if (m && m.length) {
        const key = f.palavra.toLowerCase();
        const prev = hitMap.get(key);
        hitMap.set(key, {
          palavra: f.palavra,
          count: (prev?.count ?? 0) + m.length,
          campo: prev?.campo ?? campo,
        });
      }
    }
    for (const p of compiledRules) {
      if (p.regex.test(text)) {
        alertMap.set(p.id, {
          id: p.id,
          titulo: p.titulo,
          detalhe: p.detalhe,
          severidade: p.severidade,
        });
      }
    }
  }

  const hits = Array.from(hitMap.values());
  const alertas = Array.from(alertMap.values());
  return { hits, alertas, ok: hits.length === 0 && alertas.length === 0 };
}

// Divide um texto em tokens marcando trechos proibidos para highlight.
export function tokenizeWithForbidden(
  text: string,
  palavrasProibidas: string[],
): Array<{ text: string; forbidden: boolean }> {
  if (!text) return [];
  const parts: Array<{ text: string; forbidden: boolean }> = [];
  const pattern = palavrasProibidas
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
    .join("|");
  if (!pattern) return [{ text, forbidden: false }];
  const re = new RegExp(`(${pattern})`, "gi");
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) {
      parts.push({ text: text.slice(last, m.index), forbidden: false });
    }
    parts.push({ text: m[0], forbidden: true });
    last = m.index + m[0].length;
    if (m[0].length === 0) re.lastIndex++;
  }
  if (last < text.length) parts.push({ text: text.slice(last), forbidden: false });
  return parts;
}
