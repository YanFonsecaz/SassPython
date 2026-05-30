import { PenLineIcon, Link2Icon, GaugeIcon, FileTextIcon } from "lucide-react";

/** Identificadores de ferramenta usados pelo backend (campo `ferramenta`). */
export const FERRAMENTAS = [
  "gerar_artigo",
  "inlinks_automaticos",
  "distribuir_inlinks",
  "core_web_vitals",
] as const;

/** Rótulo amigável para o identificador cru da ferramenta. Fonte única de verdade. */
export function labelFerramenta(f: string): string {
  switch (f) {
    case "gerar_artigo":
      return "Gerar artigo";
    case "inlinks_automaticos":
      return "Inlinks automáticos";
    case "distribuir_inlinks":
      return "Distribuir inlinks";
    case "core_web_vitals":
      return "Core Web Vitals";
    default:
      return f;
  }
}

/** Ícone associado à ferramenta (lucide). */
export function iconeFerramenta(f: string): React.ElementType {
  switch (f) {
    case "gerar_artigo":
      return PenLineIcon;
    case "inlinks_automaticos":
    case "distribuir_inlinks":
      return Link2Icon;
    case "core_web_vitals":
      return GaugeIcon;
    default:
      return FileTextIcon;
  }
}
