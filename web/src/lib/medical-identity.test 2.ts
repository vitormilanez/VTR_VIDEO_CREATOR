import { describe, expect, it } from "vitest";
import {
  MEDICAL_PROFESSIONAL_IDENTIFICATION,
  MEDICAL_PUBLICATION_NOTICE,
  ensureMedicalProfessionalIdentification,
  formatPublicationCaption,
  safeEditorialCta,
} from "@/lib/medical-identity";

describe("medical publication identification", () => {
  it("adds the required identification once to a Reel caption", () => {
    const caption = ensureMedicalProfessionalIdentification("Texto educativo.", 2200);

    expect(caption).toContain(MEDICAL_PROFESSIONAL_IDENTIFICATION);
    expect(caption.length).toBeLessThanOrEqual(2200);
    expect(ensureMedicalProfessionalIdentification(caption, 2200)).toBe(caption);
  });

  it("places the identification before generated hashtags", () => {
    const caption = formatPublicationCaption("Texto do carrossel.", ["saude", "#medicina"]);

    expect(caption).toBe(
      `Texto do carrossel.\n\n${MEDICAL_PUBLICATION_NOTICE}\n\n#saude #medicina`,
    );
  });

  it("replaces commercial and acquisition CTAs with the educational default", () => {
    expect(safeEditorialCta("Quer mais dicas? Siga e acompanhe.")).toBe("Salve para rever");
    expect(safeEditorialCta("Compartilhe com alguém.")).toBe("Salve para rever");
    expect(safeEditorialCta("Salve este conteúdo para consultar depois.")).toBe(
      "Salve este conteúdo para consultar depois.",
    );
  });

  it("removes a legacy acquisition CTA from an existing Reel caption", () => {
    const caption = ensureMedicalProfessionalIdentification(
      "Explicação educativa.\n\nQuer mais dicas? Siga e acompanhe.",
      2200,
    );

    expect(caption).toContain("Explicação educativa.");
    expect(caption).not.toContain("Quer mais dicas");
    expect(caption).not.toContain("Siga e acompanhe");
    expect(caption).toContain(MEDICAL_PUBLICATION_NOTICE);
  });
});
