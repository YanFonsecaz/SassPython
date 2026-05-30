export const GLOSSARIO: Record<string, string> = {
  lcp: "Largest Contentful Paint — tempo que o maior elemento visível da página leva para aparecer. Quanto menor, melhor.",
  cls: "Cumulative Layout Shift — mede a estabilidade visual da página. Mudanças inesperadas de layout (elementos que pulam) pioram essa métrica.",
  inp: "Interaction to Next Paint — tempo entre o clique/tap do usuário e a resposta visual da página. Indica quão responsiva a página se sente.",
  tbt: "Total Blocking Time — tempo total que a página fica travada antes de responder ao usuário. Causado por JavaScript pesado.",
  score: "Pontuação geral de performance (0-100), calculada pelo Google com base nas métricas acima.",
  url_canonica: "URL principal e definitiva de uma página. O Google usa essa URL como referência para indexação, evitando duplicidade.",
  template: "Tipo de página usado na análise (Home, Produto, Categoria, Blog, etc.). Cada template tem boas práticas diferentes.",
  estrategia: "Dispositivo de teste: Mobile testa como o site funciona em celulares; Desktop testa em computadores.",
  plataforma: "Dispositivo detectado automaticamente: mobile ou desktop. Usado para aplicar métricas adequadas.",
  persona: "Perfil de tom/estilo de escrita que a IA usa ao gerar conteúdo. Você pode criar diferentes personas por cliente.",
  mfa: "Autenticação de Múltiplos Fatores — camada extra de segurança que pede um código além da senha ao fazer login.",
};
