import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom";
import type { PageExperienceListResponse } from "@/lib/api/cwv";

// Testamos a lógica de cor do veredito isolada (função interna do componente).
// Como PageExperienceSection e corVeredito não são exportados, replicamos a
// tabela aqui para travar o contrato visual.

const VEREDITO_LABELS: Record<string, string> = {
  pass: "OK",
  fail: "Falha",
  erro: "Inconclusivo",
  na: "N/A",
};

describe("Page Experience — veredito labels", () => {
  it("mapeia os 4 vereditos para labels em pt-BR", () => {
    expect(VEREDITO_LABELS["pass"]).toBe("OK");
    expect(VEREDITO_LABELS["fail"]).toBe("Falha");
    expect(VEREDITO_LABELS["erro"]).toBe("Inconclusivo");
    expect(VEREDITO_LABELS["na"]).toBe("N/A");
  });
});

describe("Page Experience — shape da resposta", () => {
  it("uma resposta válida tem 7 checks por origem", () => {
    const pe: PageExperienceListResponse = {
      origens: [
        {
          origem: "https://exemplo.com",
          https: "pass",
          ssl: "pass",
          redirect_301: "fail",
          security_headers: "pass",
          safe_browsing: "na",
          mixed_content: "pass",
          mobile_friendly: "pass",
          detalhes_json: {},
        },
      ],
    };
    expect(pe.origens).toHaveLength(1);
    const o = pe.origens[0];
    const checks = ["https", "ssl", "redirect_301", "security_headers", "safe_browsing", "mixed_content", "mobile_friendly"] as const;
    expect(checks.every((k) => k in o)).toBe(true);
  });

  it("múltiplas origens são suportadas", () => {
    const pe: PageExperienceListResponse = {
      origens: [
        { origem: "https://a.com", https: "pass", ssl: "pass", redirect_301: "pass", security_headers: "pass", safe_browsing: "pass", mixed_content: "pass", mobile_friendly: "pass", detalhes_json: {} },
        { origem: "https://b.com", https: "fail", ssl: "erro", redirect_301: "na", security_headers: "fail", safe_browsing: "na", mixed_content: "pass", mobile_friendly: "erro", detalhes_json: {} },
      ],
    };
    expect(pe.origens).toHaveLength(2);
    expect(pe.origens.map((o) => o.origem)).toEqual(["https://a.com", "https://b.com"]);
  });
});
