import { describe, expect, it } from "vitest";

import { parsePodcastScript } from "@/lib/podcast-script";

describe("parsePodcastScript", () => {
  it("converts HOST and GUEST blocks into ordered turns", () => {
    expect(
      parsePodcastScript(`
HOST: Doutor, essa medicação pode superar as opções atuais?

GUEST: Ela é promissora, mas ainda está em estudo.

HOST: E os resultados?

GUEST: Precisamos interpretar os números com contexto.
      `),
    ).toEqual([
      {
        speakerId: "a",
        text: "Doutor, essa medicação pode superar as opções atuais?",
      },
      { speakerId: "b", text: "Ela é promissora, mas ainda está em estudo." },
      { speakerId: "a", text: "E os resultados?" },
      { speakerId: "b", text: "Precisamos interpretar os números com contexto." },
    ]);
  });

  it("keeps wrapped lines in the previous speaker turn", () => {
    expect(
      parsePodcastScript(
        "HOST: Qual é o ponto principal?\nDá para explicar de forma simples?\nGUEST: Sim.",
      ),
    ).toEqual([
      {
        speakerId: "a",
        text: "Qual é o ponto principal? Dá para explicar de forma simples?",
      },
      { speakerId: "b", text: "Sim." },
    ]);
  });

  it("accepts Portuguese aliases", () => {
    expect(parsePodcastScript("APRESENTADOR: Uma dúvida.\nESPECIALISTA: Uma resposta.")).toEqual([
      { speakerId: "a", text: "Uma dúvida." },
      { speakerId: "b", text: "Uma resposta." },
    ]);
  });

  it("explains unsupported labels", () => {
    expect(() => parsePodcastScript("NARRADOR: Abertura.\nGUEST: Resposta.")).toThrow(
      "Use HOST: e GUEST:",
    );
  });
});
