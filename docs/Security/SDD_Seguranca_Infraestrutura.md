# SOFTWARE DESIGN DOCUMENT (SDD)

## Segurança de Infraestrutura — SSH, TLS, Firewall e Web Application Firewall (WAF)

| Campo                | Valor                                                        |
|----------------------|--------------------------------------------------------------|
| **Título**           | Segurança de Infraestrutura: SSH, TLS, Firewall e WAF       |
| **Versão**           | 1.0                                                          |
| **Data**             | 2026-04-08                                                   |
| **Classificação**    | Confidencial                                                 |
| **Autor**            | Baseado no curso "Segurança Para Devs"                       |

---

## 1. Introdução

### 1.1 Propósito

Este documento descreve o design de segurança para a infraestrutura que hospeda aplicações web. Abrange configuração segura de SSH, certificados TLS (Let's Encrypt), firewall de rede, atualizações automáticas de segurança, criptografia em trânsito e em repouso, e Web Application Firewall (WAF / ModSecurity).

### 1.2 Escopo

- SSH seguro: autenticação por chave, criação de usuários, permissões, bloqueio de login por senha
- DNS: propagação e configuração de registros A/AAAA
- TLS/HTTPS: Let's Encrypt, Certbot, renovação automática
- Firewall de rede: regras de portas (SSH, HTTP, HTTPS)
- Atualizações automáticas: Unattended Upgrades
- Criptografia em trânsito (TLS) e em repouso (disco criptografado)
- WAF (Web Application Firewall): ModSecurity, regras, remoção seletiva

### 1.3 Definições e Acrônimos

| Termo                    | Definição                                                        |
|--------------------------|------------------------------------------------------------------|
| **SSH**                 | Secure Shell — protocolo de acesso remoto criptografado         |
| **Chave SSH**           | Par de chaves (privada + pública) para autenticação SSH           |
| **TLS**                 | Transport Layer Security — criptografia de tráfego HTTP          |
| **Let's Encrypt**       | Autoridade certificadora gratuita para certificados TLS          |
| **Certbot**             | Ferramenta para obter e renovar certificados Let's Encrypt       |
| **WAF**                 | Web Application Firewall — firewall que inspeciona tráfego HTTP  |
| **ModSecurity**         | WAF open source de referência para Apache/Nginx                 |
| **OWASP CRS**           | Core Rule Set — conjunto de regras de segurança do ModSecurity   |
| **Unattended Upgrades**  | Pacote Debian/Ubuntu que aplica atualizações de segurança automaticamente |
| **Proxy Reverso**       | Servidor web que recebe requisições e repassa para aplicação     |

### 1.4 Princípio Fundamental

> **Segurança é feita em camadas, da infraestrutura até a aplicação.** O disco criptografado (repouso), TLS no tráfego (trânsito), firewall de rede (portas), WAF (tráfego HTTP) e código seguro (aplicação) formam múltiplas barreiras. Cada camada independente adiciona proteção, mesmo que outra falhe.

---

## 2. Visão Geral de Arquitetura

### 2.1 Camadas de Segurança da Infraestrutura

```
┌──────────────────────────────────────────────────────────────────────┐
│           CAMADAS DE SEGURANÇA — INFRAESTRUTURA                    │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │  CAMADA 1 — CRIPTOGRAFIA EM REPOUSO                       │      │
│  │  • Disco do servidor criptografado (LUKS)                  │      │
│  │  • Backup criptografado                                    │      │
│  │  • Protege contra acesso físico ao disco                   │      │
│  └────────────────────────────────────────────────────────────┘      │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │  CAMADA 2 — FIREWALL DE REDE                               │      │
│  │  • Porta 22 (SSH) — apenas IPs autorizados                 │      │
│  │  • Porta 80 (HTTP) — redireciona para 443                  │      │
│  │  • Porta 443 (HTTPS) — tráfego web criptografado          │      │
│  │  • Todas as demais portas — BLOQUEADAS                     │      │
│  └────────────────────────────────────────────────────────────┘      │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │  CAMADA 3 — SSH SEGURO                                     │      │
│  │  • Autenticação por chave (não por senha)                  │      │
│  │  • Login root desabilitado (PermitRootLogin no)           │      │
│  │  • PasswordAuthentication no                                │      │
│  │  • Permissões restritivas em ~/.ssh/ (700)                │      │
│  │  • Permissões restritivas em authorized_keys (600)         │      │
│  └────────────────────────────────────────────────────────────┘      │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │  CAMADA 4 — TLS (CRIPTOGRAFIA EM TRÂNSITO)                │      │
│  │  • Certificado Let's Encrypt (gratuito)                    │      │
│  │  • Renovação automática via Certbot (cron diário)          │      │
│  │  • Redirecionamento HTTP → HTTPS                            │      │
│  └────────────────────────────────────────────────────────────┘      │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │  CAMADA 5 — WEB APPLICATION FIREWALL (WAF)                 │      │
│  │  • ModSecurity + OWASP Core Rule Set                       │      │
│  │  • Detecção de SQL Injection, RCE, LFI, XSS               │      │
│  │  • Modo Detection Only (inicial) → On (produção)          │      │
│  │  • Regras seletivas por URL (location-based)               │      │
│  └────────────────────────────────────────────────────────────┘      │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │  CAMADA 6 — ATUALIZAÇÕES AUTOMÁTICAS                       │      │
│  │  • Unattended Upgrades (pacotes de segurança)             │      │
│  │  • Atualização automática diária                           │      │
│  │  • Kernel atualizado (restart agendado)                    │      │
│  └────────────────────────────────────────────────────────────┘      │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────┐      │
│  │  CAMADA 7 — APLICAÇÃO SEGURA                               │      │
│  │  • Código seguro (tudo que foi ensinado no curso)         │      │
│  │  • Input validation, CSRF protection, etc.                 │      │
│  │  • SAST + SCA no CI/CD                                     │      │
│  └────────────────────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 Fluxo de uma Requisição Através das Camadas

```
Usuário (navegador)
    │
    ▼
┌─────────────────────────────────────────┐
│  DNS (seguro.elcio.com.br → IP)         │
└───────────────┬─────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────┐
│  FIREWALL DE REDE                       │
│  Porta 443? ✅ Permitido                │
│  Porta 22?  ✅ Permitido (SSH)          │
│  Outra porta? ❌ Bloqueado              │
└───────────────┬─────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────┐
│  TLS (HTTPS)                            │
│  Certificado Let's Encrypt válido? ✅    │
│  Handshake TLS → Tráfego criptografado  │
└───────────────┬─────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────┐
│  WAF (ModSecurity)                      │
│  Anomaly Score < 5? ✅ Libera           │
│  Anomaly Score ≥ 5? ❌ Forbidden (403)  │
│  Regras removidas por URL? ⚠️ Verifica  │
└───────────────┬─────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────┐
│  SERVIDOR WEB (Apache/Nginx)            │
│  Proxy reverso → Aplicação              │
└───────────────┬─────────────────────────┘
                │
                ▼
┌─────────────────────────────────────────┐
│  APLICAÇÃO                              │
│  Lógica de negócio + Validação          │
│  Dados salvos em disco CRIPTOGRAFADO    │
└─────────────────────────────────────────┘
```

---

## 3. Componentes de Design

### 3.1 Componente: SSH Seguro

#### 3.1.1 Descrição

Configuração segura de acesso SSH ao servidor usando autenticação por chave pública/privada, com login root desabilitado, autenticação por senha desabilitada e permissões restritivas nos arquivos de chave.

#### 3.1.2 Procedimento de Configuração

```bash
# 1. CRIAR USUÁRIO (não usar root)
adduser deploy
usermod -aG sudo deploy

# 2. CONFIGURAR SUDO SEM SENHA
echo "deploy ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/deploy
chmod 440 /etc/sudoers.d/deploy

# 3. CONFIGURAR CHAVES SSH
mkdir -p /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
echo "ssh-rsa AAAA... usuario@maquina" > /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys
chown -R deploy:deploy /home/deploy/.ssh

# 4. DESABILITAR LOGIN ROOT E SENHA
# /etc/ssh/sshd_config:
PermitRootLogin no
PasswordAuthentication no

# 5. RESTARTAR SSH (mantenha sessão aberta!)
systemctl restart sshd

# 6. TESTAR EM OUTRA JANELA ANTES DE FECHAR A ATUAL
ssh deploy@servidor
sudo whoami  # Deve retornar root
```

#### 3.1.3 Permissões Corretas

```
~/.ssh/                    → 700 (drwx------)  → Apenas o dono pode acessar
~/.ssh/authorized_keys    → 600 (-rw-------)  → Apenas o dono pode ler/escrever
~/.ssh/id_rsa             → 600 (-rw-------)  → Chave PRIVADA — nunca compartilhar
~/.ssh/id_rsa.pub         → 644 (-rw-r--r--)  → Chave PÚBLICA — pode ser compartilhada
```

#### 3.1.4 Boas Práticas para Chaves SSH

| Prática                                    | Razão                                                        |
|-------------------------------------------|----------------------------------------------------------------|
| Mantenha o mesmo par de chaves            | Evita gerenciar múltiplas chaves em múltiplos servidores    |
| Proteja a chave privada com senha         | Se o disco for comprometido, a senha protege a chave         |
| Criptografe o disco local                 | Roubo do notebook ≠ roubo das chaves                         |
| Nunca compartilhe a chave privada         | Equivalente a compartilhar senha do banco                    |
| Use `ssh-keygen -t ed25519`               | Ed25519 é mais moderno e seguro que RSA                      |

#### 3.1.5 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| SH-1 | Nunca acesse servidores como root diretamente                       | Crítica    |
| SH-2 | Crie um usuário deploy com sudo per-application                   | Alta       |
| SH-3 | Use autenticação por chave SSH (não por senha)                    | Crítica    |
| SH-4 | Desabilite `PermitRootLogin no` em sshd_config                    | Crítica    |
| SH-5 | Desabilite `PasswordAuthentication no` em sshd_config               | Crítica    |
| SH-6 | Permissões de ~/.ssh/: 700, authorized_keys: 600                   | Alta       |
| SH-7 | Teste SSH em outra janela antes de fechar a sessão atual            | Alta       |
| SH-8 | Cada desenvolvedor deve ter seu próprio usuário (não compartilhado) | Alta       |

---

### 3.2 Componente: TLS / HTTPS

#### 3.2.1 Descrição

Configuração de certificado TLS gratuito via Let's Encrypt usando Certbot. Garante criptografia em trânsito entre o navegador do usuário e o servidor. Renovação automática via cron.

#### 3.2.2 Procedimento de Configuração

```bash
# 1. INSTALAR CERTBOT
snap install classic certbot

# 2. OBTER CERTIFICADO
certbot -d seguro.exemplo.com.br

# 3. CONFIGURAR RENOVAÇÃO AUTOMÁTICA (crontab -e)
12 2 * * * /snap/bin/certbot renew

# 4. VERIFICAR
curl -I https://seguro.exemplo.com.br
# → HTTP/2 200
# → Server: Apache
```

#### 3.2.3 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| TL-1 | Todo site em produção deve usar HTTPS                               | Crítica    |
| TL-2 | Use Let's Encrypt (gratuito) ou certificado do provedor de cloud      | Alta       |
| TL-3 | Configure renovação automática do certificado (cron diário)          | Alta       |
| TL-4 | Redirecione HTTP (porta 80) para HTTPS (porta 443)                  | Alta       |
| TL-5 | Nunca use HTTP para tráfego de produção                              | Crítica    |

---

### 3.3 Componente: Firewall de Rede e Atualizações Automáticas

#### 3.3.1 Descrição

Firewall de rede que bloqueia todas as portas exceto as estritamente necessárias (SSH, HTTP, HTTPS). Atualizações automáticas de segurança via Unattended Upgrades.

#### 3.3.2 Procedimento de Configuração

```bash
# FIREWALL (exemplo: UFW)
ufw enable
ufw allow ssh      # Porta 22 — acesso administrativo
ufw allow http     # Porta 80 — redireciona para HTTPS
ufw allow https    # Porta 443 — tráfego web criptografado
# Todas as demais portas: bloqueadas por padrão

# ATUALIZAÇÕES AUTOMÁTICAS
# Verificar se Unattended Upgrades está instalado:
dpkg -l | grep unattended-upgrades

# Configurar em /etc/apt/apt.conf.d/50unattended-upgrades
# Atualizações de segurança automáticas diárias

# ATUALIZAÇÃO MANUAL
apt update && apt upgrade -y
```

#### 3.3.3 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| FW-1 | Habilite firewall — bloqueie todas as portas por padrão               | Crítica    |
| FW-2 | Abra apenas portas estritamente necessárias (SSH, HTTP, HTTPS)        | Crítica    |
| FW-3 | Instale e configure Unattended Upgrades                               | Alta       |
| FW-4 | Mantenha o servidor atualizado com `apt update && apt upgrade`         | Alta       |
| FW-5 | Agende restart de kernel em janela de manutenção                    | Média      |

---

### 3.4 Componente: Web Application Firewall (WAF)

#### 3.4.1 Descrição

WAF inspeciona o tráfego HTTP e bloqueia requisições que correspondem a padrões de ataque conhecidos (SQL Injection, RCE, LFI, XSS, etc.). Usa ModSecurity com OWASP Core Rule Set. O programador é fundamental para configurar exceções seletivas sem comprometer a segurança.

#### 3.4.2 Procedimento de Configuração

```bash
# 1. INSTALAR MODSECURITY
apt install libapache2-mod-security2
a2enmod security2

# 2. USAR CONFIGURAÇÃO RECOMENDADA
# cp /etc/modsecurity/modsecurity.conf-recommended \
#    /etc/modsecurity/modsecurity.conf

# 3. CONFIGURAR MODO — Detection Only (inicialmente)
# /etc/modsecurity/modsecurity.conf:
SecRuleEngine DetectionOnly

# 4. RESTARTAR E VERIFICAR LOGS
systemctl restart apache2
# Logs em: /var/log/modsecurity/audit.log

# 5. ATIVAR MODO BLOQUEIO (após validação)
# /etc/modsecurity/modsecurity.conf:
SecRuleEngine On

# 6. REMOVER REGRAS SELETIVAMENTE (exceções por URL)
# /etc/apache2/conf-available/waf.conf:
<Location /ajuda>
    SecRuleRemoveById 932100
    SecRuleRemoveById 941100
</Location>

a2enconf waf
systemctl restart apache2
```

#### 3.4.3 Fluxo de Decisão para Exceções no WAF

```
┌──────────────────────────────────────────────────────────────────────┐
│  REQUISIÇÃO BLOQUEADA PELO WAF — O QUE FAZER?                       │
│                                                                      │
│  1. Ler o log de auditoria: /var/log/modsecurity/audit.log           │
│     → Identificar rule ID e mensagem                                 │
│                                                                      │
│  2. O programador avalia: a requisição é legítima?                  │
│     ├── SIM → A regra está bloqueando uso legítimo                  │
│     │         → Remover regra APENAS para a URL específica          │
│     │         → Usar <Location /rota> com SecRuleRemoveById        │
│     │         → NUNCA desabilitar a regra globalmente                │
│     │                                                                │
│     └── NÃO → A requisição é um ataque real                        │
│               → Manter o bloqueio (a WAF está funcionando!)          │
│               → Investigar a origem do ataque                        │
│                                                                      │
│  ⚠️  NUNCA desative o WAF ou remova regras globalmente              │
│  ⚠️  O PROGRAMADOR é quem decide se a requisição é legítima        │
│  ⚠️  O TIME DE SEGURANÇA remove regras, o PROGRAMADOR valida        │
└──────────────────────────────────────────────────────────────────────┘
```

#### 3.4.4 Modos de Operação do ModSecurity

| Modo                | Comportamento                                    | Quando Usar                    |
|---------------------|--------------------------------------------------|--------------------------------|
| **DetectionOnly**   | Loga ameaças mas NÃO bloqueia                   | Deploy inicial em produção    |
| **On**              | Bloqueia requisições que excedem anomaly score  | Após validação em DetectionOnly |

#### 3.4.5 Regras

| ID   | Regra                                                                    | Severidade |
|------|--------------------------------------------------------------------------|------------|
| WF-1 | Instale WAF (ModSecurity ou equivalente)                              | Alta       |
| WF-2 | Use OWASP Core Rule Set (configuração recomendada)                  | Alta       |
| WF-3 | Comece em modo Detection Only para validar regras                    | Alta       |
| WF-4 | Nunca desabilite o WAF globalmente para resolver falso positivo      | Crítica    |
| WF-5 | Remova regras APENAS para URLs específicas (location-based)         | Alta       |
| WF-6 | O programador deve validar se requisição bloqueada é legítima       | Alta       |
| WF-7 | Monitore logs de auditoria periodicamente                             | Média      |

---

## 4. Matriz de Ameaças e Mitigações

| # | Ameaça                              | Camada de Defesa              | Impacto                           | Mitigação                                      | Ref. |
|---|-------------------------------------|-------------------------------|-----------------------------------|------------------------------------------------|------|
| 1 | Força bruta SSH                      | SSH seguro                     | Acesso não autorizado            | Chave SSH + sem senha + sem root                | 3.1  |
| 2 | Roubo de chave SSH                  | SSH seguro                     | Acesso total ao servidor         | Chave com senha + disco criptografado          | 3.1  |
| 3 | Interceptação de tráfego HTTP       | TLS                           | Vazamento de dados               | Let's Encrypt + redirecionamento HTTP→HTTPS     | 3.2  |
| 4 | Ataque a portas abertas             | Firewall de rede               | Acesso a serviços internos       | Bloquear todas portas exceto SSH/HTTP/HTTPS      | 3.3  |
| 5 | Exploração de CVE conhecida         | Atualizações automáticas        | RCE, DoS                         | Unattended Upgrades + `apt upgrade`            | 3.3  |
| 6 | SQL Injection via query string       | WAF                           | Bypass de autenticação           | ModSecurity OWASP CRS                           | 3.4  |
| 7 | Command Injection via query string   | WAF                           | RCE no servidor                  | ModSecurity regras 932xxx, 941xxx               | 3.4  |
| 8 | Acesso físico ao disco              | Criptografia em repouso        | Leitura de dados                 | Disco criptografado (LUKS)                        | 2.1  |

---

## 5. Checklists de Verificação

### 5.1 Checklist — Provisionamento de Servidor

- [ ] Disco criptografado ativado na criação do servidor
- [ ] Senha root gerada com CSPRNG (`openssl rand -hex 32`)
- [ ] Senha root NÃO reaproveitada de outros serviços
- [ ] Registros DNS A e AAAA criados e propagados
- [ ] Servidor atualizado (`apt update && apt upgrade`)
- [ ] Unattended Upgrades instalado e configurado

### 5.2 Checklist — SSH

- [ ] Usuário deploy criado (não usa root diretamente)
- [ ] Sudo configurado com arquivo separado em `/etc/sudoers.d/`
- [ ] Par de chaves SSH gerado (`ssh-keygen -t ed25519`)
- [ ] Chave pública colocada em `~/.ssh/authorized_keys` do servidor
- [ ] Permissões: `~/.ssh/` = 700, `authorized_keys` = 600
- [ ] `PermitRootLogin no` em `/etc/ssh/sshd_config`
- [ ] `PasswordAuthentication no` em `/etc/ssh/sshd_config`
- [ ] SSH testado em nova janela antes de fechar sessão atual
- [ ] Cada desenvolvedor tem seu próprio usuário com sua própria chave

### 5.3 Checklist — TLS e Web Server

- [ ] Certificado TLS obtido (Let's Encrypt ou provedor)
- [ ] Redirecionamento HTTP → HTTPS configurado
- [ ] Renovação automática configurada (cron diário)
- [ ] Firewall habilitado (SSH, HTTP, HTTPS apenas)
- [ ] Servidor web configurado como proxy reverso
- [ ] WAF instalado e configurado (ModSecurity)
- [ ] WAF em modo Detection Only durante estágio inicial
- [ ] WAF em modo On após validação
- [ ] Exceções do WAF são por URL (location), nunca globais

---

## 6. Tabela Comparativa — Criptografia

| Tipo                    | O que Protege                 | Como Implementar                | Quando           |
|-------------------------|--------------------------------|----------------------------------|------------------|
| **Disco criptografado** | Dados em repouso no servidor  | LUKS na criação do VPS/VM      | Provisionamento  |
| **TLS (HTTPS)**         | Tráfego entre usuário e server | Let's Encrypt + Certbot         | Setup do servidor |
| **SSH com chave**       | Acesso administrativo          | ssh-keygen + authorized_keys   | Setup do servidor |
| **TLS entre componentes**| Tráfego interno (microserviços)| Certificados internos/mTLS     | Arquitetura avançada |

---

## 7. Referências

| Recurso                      | URL/Descrição                                             |
|------------------------------|-----------------------------------------------------------|
| Let's Encrypt                | https://letsencrypt.org/                                  |
| Certbot                      | https://certbot.eff.org/                                  |
| OWASP ModSecurity            | https://owasp.org/www-project-modsecurity/                 |
| OWASP Core Rule Set          | https://coreruleset.org/                                   |
| Mozilla SSL Configuration    | https://ssl-config.mozilla.org/                            |
| SSH Key Management           | https://www.ssh.com/academy/ssh/key-management             |
| UFW Documentation            | https://wiki.ubuntu.com/UncomplicatedFirewall              |
| Unattended Upgrades          | https://wiki.debian.org/UnattendedUpgrades                 |
