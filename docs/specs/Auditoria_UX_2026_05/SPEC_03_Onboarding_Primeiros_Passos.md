# SPEC 03 — Onboarding e Primeiros Passos

**Status:** a aplicar · **Escopo:** frontend (fluxos de cliente/persona/ferramentas) · **Severidade:** 🔴 Alta · **Esforço:** ~4h
**Índice:** [Auditoria UX 2026-05](README.md)

## 1. Problema

### 1.1 Dead-end de persona no Gerar Artigo
Em `src/components/ferramentas/formulario-gerar-artigo.tsx`:
- `canAdvance()` no passo 0 exige **persona obrigatória**: `case 0: return !!clientId && !!personaId;` (`:77`).
- O `<select>` de persona (`:218-231`) lista apenas `clienteSelecionado?.config_json?.personas` (personas **específicas**). Um cliente recém-criado pode ter **só `persona_global`** e **zero personas específicas** → dropdown vazio ("Selecione uma persona"), botão "Próximo" desabilitado, **sem nenhuma saída** (não há "criar persona" nem link). O usuário não entende por que está travado.

Contexto: personas são criadas dentro do form de cliente (`FormularioPersona`, renderizado por `formulario-cliente.tsx`), então para desbloquear o usuário teria que sair, editar o cliente, voltar — sem nenhuma indicação disso.

### 1.2 Form de cliente denso e cheio de jargão
`src/components/clientes/formulario-cliente.tsx`:
- "Persona Global" com campos de **texto livre**: "Tom de voz", "Nível técnico", "Estilo de escrita", "Instruções gerais" (`:124-201`). Para leigo, não há pistas de valores válidos (apesar dos placeholders) nem explicação do que é "Persona Global" vs "Personas específicas".
- Erro exibido como `<p className="text-sm text-destructive">` cru (`:93-97`) — sem caixa, destoa do padrão.

### 1.3 Sem fio condutor de primeiro uso
Recém-cadastrado, o usuário não tem clientes; sem cliente, nenhuma ferramenta funciona. Só o CWV trata bem o estado "nenhum cliente" (`cwv-form.tsx` mostra link "Cadastrar cliente"). Falta um padrão global de "comece por aqui".

## 2. Objetivos
1. **Eliminar o dead-end de persona**: permitir avançar usando a persona padrão do cliente **ou** criar persona inline/por link.
2. Tornar o form de cliente **compreensível** para leigo (explicação + presets onde fizer sentido).
3. Dar um **fio condutor de primeiro uso** consistente (sem clientes → CTA claro).

## 3. Mudanças propostas

### 3.1 Persona opcional / com padrão (o dead-end)
Opção recomendada (menor atrito): tornar a persona **não obrigatória**, usando a Persona Global do cliente como padrão.
- No `<select>` de persona, primeira opção = **"Padrão do cliente (Persona Global)"** com `value=""` válido; `canAdvance` passo 0 passa a exigir só `clientId`.
- Enviar `persona_id` vazio/"global" quando o usuário não escolher específica (confirmar contrato do backend `/ferramentas/gerar-artigo`; se exigir string, mandar `"global"` ou o nome da persona_global).
- Quando o cliente **tem** personas específicas, elas continuam listadas após a opção padrão.
- Complementar: ao lado do select, link **"Gerenciar personas"** → `/clientes/{clientId}` (ou abrir o form de cliente), para quem quiser criar uma específica.

### 3.2 Form de cliente mais guiado
- Bloco introdutório curto no topo (padrão `inlinks-seletor-modo.tsx`): "O que é um cliente aqui? É o site/marca para o qual a IA vai escrever. A **Persona Global** define o tom padrão; **Personas específicas** são variações para públicos diferentes (opcional)."
- "Persona Global": manter texto livre, mas adicionar **exemplos clicáveis**/hint abaixo de cada campo (ou converter "Tom de voz"/"Nível técnico"/"Estilo de escrita" em `Select` com presets + opção "Outro"). Decisão de presets fica com a implementação; mínimo = hints.
- Trocar o erro cru por caixa padrão (ver [[SPEC_05_Design_System_Consistencia]]).
- Deixar explícito que **Personas específicas são opcionais** (já há texto; reforçar visualmente).

### 3.3 Fio condutor de primeiro uso
- Padronizar empty state "nenhum cliente" nas ferramentas (Gerar Artigo, Inlinks, CWV) com o mesmo CTA "Cadastrar primeiro cliente" → `/clientes/novo`.
- No hub `(app)/ferramentas/page.tsx`, quando `clientes.length === 0` (via `useClientes`), exibir um banner discreto "Comece cadastrando um cliente" acima dos cards de ferramenta.

## 4. Critérios de aceite
- [ ] Cliente **sem personas específicas** → Gerar Artigo avança do passo 0 usando "Padrão do cliente", **sem travar**.
- [ ] Geração conclui com persona padrão (backend aceita o valor enviado).
- [ ] Form de cliente exibe explicação do que é cliente/persona e marca personas específicas como opcionais.
- [ ] Usuário sem clientes vê CTA claro "cadastrar cliente" no hub e em cada ferramenta.

## 5. Verificação E2E
Criar cliente novo **sem** persona específica → abrir Gerar Artigo → confirmar avanço e geração (mock/observar request). Zerar clientes (ou usuário novo) → confirmar CTAs de onboarding.

## 6. Notas / decisão em aberto
- **Confirmar contrato** de `persona_id` no backend antes de tornar opcional (pode exigir ajuste de schema — registrar, não implementar agora se for backend).
- Se preferir manter persona obrigatória, alternativa é **criar persona inline** no passo 0 (reusar `FormularioPersona`) — porém exige persistir no cliente; mais complexo. A opção 3.1 (padrão global) é a recomendada.
- Relacionado: [[SPEC_04_Microcopy_Acentos_Jargao]], [[SPEC_05_Design_System_Consistencia]].
