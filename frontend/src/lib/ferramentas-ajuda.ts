// Conteúdo de ajuda "Como usar" por ferramenta, em linguagem simples para
// usuários não técnicos. Consumido pelo componente <ComoUsar />.

export interface AjudaFerramenta {
  titulo: string;
  paraQueServe: string;
  passos: string[];
  dica?: string;
}

export const AJUDA_FERRAMENTAS: Record<string, AjudaFerramenta> = {
  "gerar-artigo": {
    titulo: "Gerar Artigo",
    paraQueServe:
      "Cria um artigo de blog otimizado para aparecer no Google, escrito pela inteligência artificial a partir do tema que você indicar — pronto para revisar e publicar, sem precisar escrever do zero.",
    passos: [
      "Escolha o cliente para quem o artigo será escrito.",
      "Informe o tema ou a palavra-chave principal e quem vai ler.",
      "Ajuste o tom e o estilo (a “persona”) se quiser, ou deixe o padrão.",
      "Clique em Gerar e aguarde a IA escrever.",
      "Revise o texto, edite o que quiser e baixe ou copie o artigo.",
    ],
    dica: "Quanto mais específico o tema (ex.: “benefícios do colágeno para a pele”, em vez de só “colágeno”), melhor o resultado.",
  },
  inlinks: {
    titulo: "Inlinks Internos",
    paraQueServe:
      "Cria links entre as páginas do seu próprio site (os “links internos”). Eles ajudam o Google a entender o site, espalham relevância entre as páginas e melhoram o SEO e a navegação de quem lê.",
    passos: [
      "Escolha o modo: receber sugestões de links dentro de um artigo, ou distribuir uma página para várias outras.",
      "Cole os endereços (URLs) das páginas envolvidas.",
      "Clique em Gerar e aguarde a IA analisar.",
      "Revise as sugestões de links e aprove as que fizerem sentido.",
    ],
    dica: "Funciona melhor em páginas que já têm bom conteúdo — os links internos potencializam o que já existe.",
  },
  "core-web-vitals": {
    titulo: "Core Web Vitals",
    paraQueServe:
      "Mede a velocidade e a estabilidade das suas páginas (a experiência de quem acessa pelo celular e pelo computador) — pontos que o Google usa para ranquear — e entrega um plano de correção página por página, em linguagem clara.",
    passos: [
      "Escolha o cliente e cole os endereços (URLs) das páginas que quer analisar.",
      "Confirme o custo e clique em Analisar.",
      "Aguarde a análise (alguns minutos por página).",
      "Leia o plano de ação por página e aplique — ou encaminhe para quem cuida do site.",
      "Depois das correções, re-analise para acompanhar a evolução.",
    ],
    dica: "Comece pelas páginas mais importantes: home, categorias e os produtos mais acessados.",
  },
  parecer: {
    titulo: "Parecer Técnico",
    paraQueServe:
      "Transforma prints de tela + uma descrição rápida de um problema de SEO em um documento técnico profissional, pronto para enviar à agência (ou ao time) aplicar as correções. A IA analisa as imagens e escreve o parecer no padrão da casa.",
    passos: [
      "Escolha o cliente.",
      "No editor, cole os prints (Ctrl/Cmd + V) e escreva, em poucas palavras, o que está errado.",
      "Clique em Gerar Parecer e aguarde a IA analisar as imagens e redigir.",
      "Revise e edite o texto direto na tela, se precisar.",
      "Clique em Baixar .docx para enviar o documento.",
    ],
    dica: "Cole o print já mostrando o problema (a aba de performance, o código, a imagem) — a IA usa a imagem somada à sua descrição para escrever.",
  },
};
