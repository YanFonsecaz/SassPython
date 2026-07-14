import { describe, expect, it } from "vitest";
import { corClassificacao, corEsforco, corCruxBucket, rotuloCruxBucket, rotuloEsforco } from "../thresholds";

describe("corClassificacao", () => {
  it("retorna tokens de sucesso para bom", () => {
    const c = corClassificacao("bom");
    expect(c.text).toBe("text-success");
    expect(c.bg).toBe("bg-success/10");
  });

  it("retorna tokens destrutivos para ruim", () => {
    const c = corClassificacao("ruim");
    expect(c.text).toBe("text-destructive");
  });

  it("retorna muted para null", () => {
    const c = corClassificacao(null);
    expect(c.text).toBe("text-muted-foreground");
  });
});

describe("corEsforco (SPEC_CWV_Estimador_Esforco)", () => {
  it("baixo = success", () => {
    expect(corEsforco("baixo").text).toBe("text-success");
  });
  it("medio = ambar", () => {
    expect(corEsforco("medio").text).toBe("text-yellow-600");
  });
  it("alto = destructive", () => {
    expect(corEsforco("alto").text).toBe("text-destructive");
  });
  it("rotuloEsforco mapeia corretamente", () => {
    expect(rotuloEsforco("baixo")).toBe("Baixo");
    expect(rotuloEsforco("medio")).toBe("Médio");
    expect(rotuloEsforco("alto")).toBe("Alto");
    expect(rotuloEsforco(null)).toBe("—");
  });
});

describe("corCruxBucket (SPEC_CWV_Field_Data)", () => {
  it("FAST = success", () => {
    expect(corCruxBucket("FAST").text).toBe("text-success");
  });
  it("AVERAGE = ambar", () => {
    expect(corCruxBucket("AVERAGE").text).toBe("text-yellow-600");
  });
  it("SLOW = destructive", () => {
    expect(corCruxBucket("SLOW").text).toBe("text-destructive");
  });
  it("rotuloCruxBucket em pt-BR", () => {
    expect(rotuloCruxBucket("FAST")).toBe("Rápido");
    expect(rotuloCruxBucket("AVERAGE")).toBe("Médio");
    expect(rotuloCruxBucket("SLOW")).toBe("Lento");
    expect(rotuloCruxBucket(null)).toBe("Sem dados");
  });
});
