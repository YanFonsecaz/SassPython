
  # PRD do SaaS de SEO com IA

  ## Resumo

  A plataforma é um SaaS de ferramentas de SEO com IA voltado para usuários não técnicos. O sistema deve permitir
  acesso seguro por login, organização do trabalho por cliente e uso de ferramentas com o menor nível possível de
  configuração manual. A experiência deve ser simples, clara e orientada a resultado. O acesso às funcionalidades é
  controlado por um sistema de créditos, que unifica o consumo de todas as ferramentas em um saldo global.
2
  ## O Que o Sistema Faz
b
  - O sistema permite que o usuário crie conta e faça login para acessar a plataforma.
  - O sistema exige autenticação para qualquer área com dados privados.
  - O sistema permite que cada usuário cadastre, edite e remova seus próprios clientes.
  - O sistema organiza o uso das ferramentas em torno dos clientes do próprio usuário quando a ferramenta exigir
    contexto específico.
  - O sistema permite que determinadas ferramentas tenham configurações próprias por cliente.
  - O sistema deve deixar claro para o usuário qual cliente está ativo no momento de uso de uma ferramenta.
  - O sistema deve reaproveitar informações já cadastradas para reduzir retrabalho e excesso de configuração.
  - O sistema deve apresentar as ferramentas com linguagem simples, navegação fácil e entendimento imediato.
  - O sistema deve conduzir o usuário ao primeiro resultado com poucos passos e pouca necessidade de configuração
    técnica.
  - O sistema deve permitir que ferramentas diferentes tenham regras próprias, desde que respeitem o isolamento por
    usuário e, quando aplicável, por cliente.
  - O sistema controla o uso de todas as ferramentas por meio de um saldo de créditos, que é descontado a cada ação
    executada.

  ## Escopo Funcional

  ### Acesso e conta

  - Cadastro de usuário.
  - Login e saída da conta.
  - Acesso restrito a usuários autenticados.

  ### Gestão de clientes

  - Cadastro de clientes do próprio usuário.
  - Edição de clientes do próprio usuário.
  - Remoção de clientes do próprio usuário.
  - Associação de configurações específicas aos clientes, quando necessário para alguma ferramenta.

  ### Ferramentas de SEO com IA

  - Cada ferramenta pode ter sua própria regra de negócio.
  - Sempre que uma ferramenta depender de contexto do cliente, o sistema deve permitir selecionar um cliente do
    próprio usuário.
  - Sempre que uma ferramenta depender de configurações por cliente, essas configurações devem ser salvas e
    reutilizadas naquele contexto.
  - A ferramenta de criação de conteúdo é um exemplo dessa regra:
  - O usuário pode criar um card do cliente.
  - O usuário pode informar nome do cliente.
  - O usuário pode definir persona do redator.
  - O usuário pode informar palavras proibidas.
  - O usuário pode definir como o redator deve agir.
  - Essas definições devem influenciar o comportamento da ferramenta para aquele cliente.
  - O mesmo princípio pode ser aplicado a outras ferramentas que também precisem de configuração específica por
    cliente.

  ### Experiência do usuário

  - O front-end deve ser totalmente focado em facilidade de uso.
  - O acesso às funcionalidades deve ser simples e direto.
  - A navegação deve ser fácil de entender para quem não é técnico.
  - O sistema deve pedir o mínimo possível de configuração antes de entregar valor.
  - Configurações mais avançadas não podem atrapalhar o fluxo principal.

  ## Regras de Negócio

  ### Regras gerais

  - Cada conta do MVP pertence a um único usuário.
  - Cada cliente pertence a um único usuário.
  - Um usuário pode ter vários clientes.
  - Um cliente não pode existir sem dono.
  - Todo dado gerado ou salvo dentro da plataforma deve estar vinculado ao usuário que o criou.
  - Quando houver contexto de cliente, o dado também deve ficar vinculado ao cliente correto.
  - Configurações de um cliente não podem ser aplicadas automaticamente a outro cliente.
  - Uma ferramenta só pode usar clientes pertencentes ao usuário autenticado.
  - O sistema deve preservar a separação entre usuários em qualquer funcionalidade.
  - O sistema deve reduzir atrito operacional para usuários não técnicos.
  - A plataforma deve priorizar clareza e simplicidade acima de flexibilidade excessiva no primeiro uso.

  ### Regras de créditos

  - Toda ação que consome recursos computacionais (LLM, embeddings, processamento) desconta créditos do saldo do
    usuário.
  - O limite de uso é global (saldo de créditos), não por ferramenta.
  - O usuário pode usar qualquer ferramenta livremente, desde que tenha saldo suficiente.
  - Antes de executar uma ação, o sistema deve informar quantos créditos serão consumidos.
  - Créditos são descontados apenas após a execução bem-sucedida da ação. Ações com falha não consomem créditos.
  - O sistema deve exibir o saldo de créditos atualizado de forma visível e permanente na interface.
  - O sistema deve alertar o usuário quando restarem 20% ou menos dos créditos do plano.
  - O sistema deve alertar o usuário quando o saldo atingir zero, oferecendo opções de upgrade ou compra de créditos
    extras.
  - Quando o saldo está zerado, o usuário pode visualizar histórico e dados salvos, mas não pode executar novas ações
    que consumam créditos.
  - O limite de clientes é definido pelo plano do usuário, não pelos créditos.

  ## Sistema de Créditos

  ### Conceito de crédito

  Um crédito é a unidade de medida de consumo da plataforma. Ele representa o custo computacional agregado de cada
  ação: chamadas a LLM (tokens de entrada e saída), geração de embeddings, processamento semântico e armazenamento
  temporário. Cada ação tem um custo fixo em créditos, definido com base em três fatores:

  1. Custo real de API — quantidade de tokens consumidos e chamadas realizadas.
  2. Complexidade da tarefa — ações que envolvem múltiplas chamadas ou análise profunda custam mais.
  3. Valor percebido pelo usuário — ações que geram resultado de alto valor (ex: artigo completo) têm custo
     proporcional.

  Este modelo é superior a limites por ferramenta porque:
  - Elimina a frustração de ter limite em uma ferramenta e saldo ocioso em outra.
  - Simplifica o modelo mental do usuário (um saldo em vez de N limites).
  - Permite adicionar novas ferramentas sem redefinir limites por funcionalidade.
  - Incentiva o uso livre e descoberta de todas as funcionalidades.

  ### Custo por ação

  | Ação | Créditos | Justificativa |
  |---|---|---|
  | Gerar artigo completo | 25 | Múltiplas chamadas LLM, alto token count |
  | Gerar outline/estrutura | 8 | LLM moderado, planejamento de conteúdo |
  | Mapear interlinks | 12 | Embeddings + análise semântica |
  | Revisar conteúdo | 10 | LLM com alto volume de tokens de entrada |
  | Gerar FAQ | 5 | LLM moderado |
  | Analisar palavras-chave | 6 | LLM + possível embedding |
  | Gerar dados estruturados (Schema) | 4 | LLM simples com template |
  | Gerar H1 | 3 | Chamada LLM simples, baixo token |
  | Gerar meta description | 3 | Chamada LLM simples |
  | Gerar title tag | 3 | Chamada LLM simples |

  ### Estrutura de planos

  | | Free | Pro | Business |
  |---|---|---|---|
  | Créditos por mês | 50 | 500 | 2.000 |
  | Preço | R$ 0 | R$ 97/mês | R$ 247/mês |
  | Artigos equivalentes | ~2 | ~20 | ~80 |
  | Limite de clientes | 3 | 15 | Ilimitado |
  | Créditos extras | Não | Sim | Sim |
  | Posicionamento | Testar e sentir valor | Profissional autônomo / pequena agência | Agência / equipe de conteúdo |

  - Todos os planos dão acesso completo a todas as ferramentas. A diferença está no volume de créditos e no limite
    de clientes.
  - Créditos do plano são renovados mensalmente (no dia do aniversário de cobrança).
  - Créditos não utilizados não acumulam para o mês seguinte.
  - O custo por crédito diminui conforme o plano avança (Free: não aplicável, Pro: R$ 0,194/crédito, Business:
    R$ 0,124/crédito).

  ### Créditos extras (add-ons)

  | Pacote | Créditos | Preço |
  |---|---|---|
  | Boost 100 | 100 | R$ 29 |
  | Boost 500 | 500 | R$ 97 |
  | Boost 1.500 | 1.500 | R$ 197 |

  - Créditos extras estão disponíveis apenas para planos pagos (Pro e Business).
  - Créditos extras não expiram — ficam disponíveis até serem consumidos, mesmo após renovação do plano.
  - O sistema deve consumir primeiro os créditos do plano e, depois, os créditos extras.

  ### Simulação de uso

  Exemplo de um usuário no plano Pro (500 créditos/mês), agência com 5 clientes:

  | Semana | Ações | Créditos |
  |---|---|---|
  Semana 1 | 4 artigos (100) + 8 meta descriptions (24) | 124 |
  Semana 2 | 3 artigos (75) + 3 revisões (30) + 5 H1s (15) | 120 |
  Semana 3 | 5 artigos (125) + 2 mapeamentos de interlinks (24) | 149 |
  Semana 4 | 2 artigos (50) + 4 FAQs (20) + 4 title tags (12) | 82 |
  | **Total** | | **475 / 500** |

  O usuário consome 95% dos créditos, sente que o plano vale a pena e fica perto do limite — o que incentiva
  upgrade ou compra de pacote extra de forma natural, sem travar a experiência.

  ## O Que É Proibido

  - Um usuário ver dados de outro usuário.
  - Um usuário editar dados de outro usuário.
  - Um usuário apagar dados de outro usuário.
  - Um usuário remover clientes de outro usuário.
  - Uma ferramenta acessar configurações de cliente pertencente a outro usuário.
  - Misturar clientes, históricos, resultados ou configurações de usuários diferentes.
  - Exigir conhecimento técnico como condição para uso normal da plataforma.
  - Obrigar o usuário a preencher muitas configurações antes de usar uma ferramenta.
  - Tornar o fluxo principal dependente de configurações avançadas.
  - Deixar ambíguo qual cliente está em uso em uma ferramenta que depende desse contexto.
  - Descontar créditos de uma ação que falhou ou não foi concluída com sucesso.
  - Limitar o uso de ferramentas individualmente (o limite é sempre global, por saldo de créditos).
  - Impedir o usuário de visualizar dados e histórico quando os créditos estiverem zerados.

  ## Cenários de Validação

  - Um usuário autenticado consegue acessar apenas os próprios dados.
  - Um usuário consegue cadastrar e remover apenas os próprios clientes.
  - Um usuário não consegue apagar dados de outro usuário.
  - Uma ferramenta com contexto por cliente só aceita clientes do usuário logado.
  - A ferramenta de conteúdo aplica corretamente nome do cliente, persona do redator, palavras proibidas e instruções
    de comportamento.
  - Outra ferramenta futura também pode usar configurações próprias por cliente sem quebrar a regra de isolamento.
  - Um usuário não técnico consegue entender o fluxo principal sem depender de conhecimento técnico.
  - O sistema informa o custo em créditos antes de executar qualquer ação.
  - Créditos são descontados apenas quando a ação é concluída com sucesso.
  - Um usuário com saldo zero consegue visualizar histórico e dados salvos, mas não consegue executar novas ações.
  - O sistema alerta o usuário quando restam 20% dos créditos e quando o saldo atinge zero.
  - O saldo de créditos está sempre visível na interface.
  - Créditos extras são consumidos após os créditos do plano.
  - Créditos não utilizados no plano não acumulam para o mês seguinte.

  ## Premissas Já Definidas

  - O MVP é de conta individual.
  - O sistema de cobrança é baseado em créditos, com planos mensais e pacotes extras.
  - A ferramenta de conteúdo é apenas um exemplo de regra de negócio por ferramenta.
  - O produto é uma suite de ferramentas de SEO com IA, não uma ferramenta única.
  - Créditos do plano não são acumulativos entre meses.
  - Créditos extras (add-ons) não expiram.
  - O custo por crédito diminui conforme o plano avança (economia de escala).
  - Todos os planos dão acesso a todas as ferramentas sem restrição por funcionalidade.
