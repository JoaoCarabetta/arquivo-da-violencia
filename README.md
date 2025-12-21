<div align="center">

# 🚨 Arquivo da Violência

### Monitoramento de Mortes Violentas no Brasil em Tempo Real

*Dados abertos para pesquisa, jornalismo e sociedade civil*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)](https://www.docker.com/)
[![Contributions Welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg)](CONTRIBUTING.md)

[🌐 Site Público](http://localhost) • [📊 Ver Dados](http://localhost/dados) • [📖 Documentação](#documentação) • [🤝 Contribuir](#como-contribuir)

</div>

---

## 📖 Sobre o Projeto

O **Arquivo da Violência** é um sistema automatizado de monitoramento de mortes violentas no Brasil, coletando e estruturando dados em tempo real a partir de fontes jornalísticas.

### 🎯 O Problema

A violência é um dos maiores problemas do Brasil, mas os dados oficiais:
- 📅 São divulgados **apenas anualmente**
- 🐢 Demoram meses ou anos para serem consolidados
- 🔒 Frequentemente são **incompletos** ou de difícil acesso
- 🗺️ Não permitem **monitoramento em tempo real**

### 💡 Nossa Solução

Criamos um sistema que:
- 🤖 **Coleta automaticamente** notícias de veículos jornalísticos
- 🧠 **Extrai informações estruturadas** usando LLMs (Large Language Models)
- 🔍 **Deduplica eventos** mencionados em múltiplas fontes
- 📊 **Disponibiliza dados abertos** para download (CSV/JSON)
- 🌐 **Interface pública** com estatísticas em tempo real

---

## ✨ Funcionalidades

### 🌍 Site Público
- **Dashboard em tempo real** com estatísticas atualizadas
- **Linha do tempo de eventos** com filtros por estado e tipo
- **Gráficos interativos** de tendências e distribuições
- **Download de dados** em CSV e JSON
- **API pública** para integração com outras ferramentas

### 🔐 Painel Administrativo
- Monitoramento do pipeline de coleta
- Gerenciamento de fontes e eventos
- Visualização de jobs e status
- Sistema de filas (ARQ + Redis)

---

## 🏗️ Arquitetura

```
┌─────────────────┐
│  Google News    │
│  RSS Feeds      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐     ┌─────────────────┐
│   Ingest        │────▶│   Download      │
│   (Discover)    │     │   (Fetch HTML)  │
└─────────────────┘     └────────┬────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │   Extract       │
                        │   (LLM Parse)   │
                        └────────┬────────┘
                                 │
                                 ▼
                        ┌─────────────────┐     ┌─────────────────┐
                        │   Enrich        │────▶│   SQLite DB     │
                        │   (Dedupe)      │     │   (Storage)     │
                        └─────────────────┘     └─────────────────┘
                                                          │
                                                          ▼
                                                 ┌─────────────────┐
                                                 │   API REST      │
                                                 │   (Public +     │
                                                 │    Admin)       │
                                                 └────────┬────────┘
                                                          │
                                                          ▼
                                                 ┌─────────────────┐
                                                 │   React SPA     │
                                                 │   (Frontend)    │
                                                 └─────────────────┘
```

### 🔧 Stack Tecnológica

**Backend:**
- 🐍 Python 3.11+ com FastAPI
- 🗄️ SQLite + SQLModel (ORM)
- 📮 ARQ (async task queue) + Redis
- 🤖 Google Gemini (LLM para extração)
- 🌐 Trafilatura (extração de conteúdo web)

**Frontend:**
- ⚛️ React 18 + TypeScript
- 🎨 TailwindCSS + shadcn/ui
- 📊 Recharts (visualização de dados)
- 🔄 TanStack Query (data fetching)
- 🛣️ React Router (navegação)

**Infraestrutura:**
- 🐳 Docker + Docker Compose
- 🔐 JWT para autenticação
- 🌐 Nginx (reverse proxy)

---

## 🚀 Quick Start

### Pré-requisitos

- Docker e Docker Compose instalados
- Chave de API do Google Gemini ([obtenha aqui](https://aistudio.google.com/app/apikey))

### 1️⃣ Clone o repositório

```bash
git clone https://github.com/JoaoCarabetta/arquivo-da-violencia.git
cd arquivo-da-violencia
```

### 2️⃣ Configure as variáveis de ambiente

```bash
cp env.example .env
```

Edite o arquivo `.env` e adicione sua chave do Gemini:

```env
# Chave da API Gemini (OBRIGATÓRIO)
GEMINI_API_KEY=sua-chave-aqui

# Credenciais do admin (mude em produção!)
JWT_SECRET_KEY=$(openssl rand -hex 32)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=sua-senha-segura

# Configurações opcionais
ENABLE_CRON=true  # Habilitar coleta automática a cada hora
DEBUG=false
```

### 3️⃣ Inicie os serviços

```bash
./docker-up.sh
# ou
docker compose up -d --build
```

### 4️⃣ Execute as migrações do banco de dados

```bash
docker compose exec api alembic upgrade head
```

### 5️⃣ Acesse a aplicação

- **Site público:** http://localhost
- **Painel admin:** http://localhost/admin
- **API docs:** http://localhost:8000/docs

---

## 📚 Documentação

### Pipeline de Dados

O sistema funciona em 4 etapas principais:

#### 1. **Ingest** 🔍
Busca notícias no Google News RSS feeds usando queries específicas (ex: "homicídio São Paulo").

#### 2. **Download** 📥
Baixa o conteúdo HTML completo das URLs encontradas e extrai o texto limpo.

#### 3. **Extract** 🧠
Usa um LLM (Gemini) para extrair informações estruturadas:
- Tipo de morte (homicídio, feminicídio, chacina, etc.)
- Local (cidade, estado, bairro)
- Data e hora
- Número de vítimas
- Envolvimento de forças de segurança
- Perfil das vítimas (quando disponível)

#### 4. **Enrich** 🔗
Deduplica eventos mencionados em múltiplas fontes e enriquece os dados.

### API Endpoints

#### Públicos (sem autenticação)

```bash
# Estatísticas gerais
GET /api/public/stats

# Mortes por tipo
GET /api/public/stats/by-type

# Mortes por estado
GET /api/public/stats/by-state

# Série temporal diária
GET /api/public/stats/by-day?days=30

# Listar eventos (com filtros)
GET /api/public/events?state=SP&type=Homicidio&page=1

# Download de dados
GET /api/public/events/export?format=csv
```

#### Admin (requer JWT)

```bash
# Login
POST /api/auth/login

# Triggers do pipeline
POST /api/pipeline/ingest?query=feminicidio&when=3d
POST /api/pipeline/download?limit=50
POST /api/pipeline/extract?limit=10
POST /api/pipeline/enrich/{event_id}

# Monitoramento
GET /api/stats
GET /api/sources
GET /api/raw-events
GET /api/unique-events
```

### Desenvolvimento Local

Para desenvolver sem Docker:

#### Backend

```bash
cd backend

# Instalar dependências com uv
uv sync

# Ativar ambiente virtual
source .venv/bin/activate

# Rodar servidor
uvicorn app.main:app --reload

# Rodar testes
pytest
```

#### Frontend

```bash
cd frontend

# Instalar dependências
npm install

# Rodar dev server
npm run dev

# Build para produção
npm run build
```

---

## 🤝 Como Contribuir

Adoramos contribuições da comunidade! Há várias formas de ajudar:

### 🐛 Reportar Bugs

Encontrou um bug? [Abra uma issue](https://github.com/JoaoCarabetta/arquivo-da-violencia/issues/new) com:
- Descrição clara do problema
- Passos para reproduzir
- Comportamento esperado vs. atual
- Screenshots (se aplicável)
- Ambiente (OS, Docker version, etc.)

### 💡 Sugerir Funcionalidades

Tem uma ideia? [Crie uma issue](https://github.com/JoaoCarabetta/arquivo-da-violencia/issues/new) descrevendo:
- Qual problema a funcionalidade resolve
- Como você imagina que funcionaria
- Por que seria útil para a comunidade

### 🔧 Contribuir com Código

1. **Fork** o repositório
2. **Clone** seu fork: `git clone https://github.com/seu-usuario/arquivo-da-violencia.git`
3. **Crie uma branch**: `git checkout -b feature/minha-feature`
4. **Faça suas mudanças** e commit: `git commit -m 'Adiciona nova feature'`
5. **Push** para o GitHub: `git push origin feature/minha-feature`
6. **Abra um Pull Request** descrevendo suas mudanças

#### Diretrizes

- Siga o estilo de código existente
- Adicione testes para novas funcionalidades
- Atualize a documentação quando necessário
- Commits em português ou inglês são aceitos

### 📖 Melhorar a Documentação

Documentação nunca é demais! PRs para:
- Corrigir erros de digitação
- Clarificar instruções
- Adicionar exemplos
- Traduzir para outros idiomas

são sempre bem-vindos!

### 💬 Participar da Comunidade

- ⭐ Dê uma estrela no projeto
- 🐦 Compartilhe nas redes sociais
- 📧 Entre em contato: [joao.carabetta@gmail.com](mailto:joao.carabetta@gmail.com)

---

## 🗺️ Roadmap

### Versão Atual (v1.0)

- ✅ Pipeline completo de coleta e extração
- ✅ Site público com estatísticas em tempo real
- ✅ Painel administrativo
- ✅ API REST pública
- ✅ Download de dados (CSV/JSON)
- ✅ Autenticação JWT

### Próximas Versões

**v1.1 - Melhorias de UX**
- [ ] Mapa interativo de eventos
- [ ] Comparação entre períodos
- [ ] Notificações por e-mail para novos eventos
- [ ] Modo escuro

**v1.2 - Dados Históricos**
- [ ] Importação de dados históricos
- [ ] Análise de tendências temporais
- [ ] Comparações ano a ano

**v1.3 - Expansão de Fontes**
- [ ] Suporte a mais fontes jornalísticas
- [ ] Integração com dados oficiais (quando disponíveis)
- [ ] Verificação cruzada de fontes

**v2.0 - Analytics Avançado**
- [ ] Machine Learning para classificação automática
- [ ] Detecção de padrões e anomalias
- [ ] Predição de tendências
- [ ] API GraphQL

---

## ⚠️ Limitações Importantes

**Este projeto tem limitações metodológicas importantes:**

1. **Cobertura parcial:** Dependemos de notícias publicadas. Muitos casos não são noticiados.
2. **Viés jornalístico:** A cobertura midiática pode ter vieses geográficos, sociais e econômicos.
3. **Precisão do LLM:** A extração automática pode conter erros. Sempre verifique a fonte original.
4. **Deduplicação:** Múltiplas notícias sobre o mesmo evento podem não ser sempre identificadas como duplicatas.
5. **Dados não oficiais:** Este NÃO é um sistema oficial. Use como complemento, não substituto, de dados oficiais.

**Use os dados com responsabilidade e contexto adequado.**

---

## 📊 Categorias de Mortes

O sistema classifica mortes violentas em:

- **Homicídio:** Morte intencional de uma pessoa por outra
- **Feminicídio:** Homicídio de mulher por razões de gênero
- **Latrocínio:** Roubo seguido de morte
- **Chacina:** Múltiplas mortes no mesmo evento (geralmente 3+)
- **Morte em confronto:** Mortes durante operações policiais
- **Linchamento:** Morte causada por multidão
- **Outro:** Outras formas de morte violenta

---

## 📄 Licença

Este projeto é licenciado sob a [Licença MIT](LICENSE) - veja o arquivo LICENSE para detalhes.

**Isso significa que você pode:**
- ✅ Usar comercialmente
- ✅ Modificar
- ✅ Distribuir
- ✅ Uso privado

**Desde que:**
- 📄 Inclua a licença e copyright
- 📄 Documente mudanças significativas

---

## 🙏 Agradecimentos

Este projeto só é possível graças a:

- **Comunidade open source** por ferramentas incríveis
- **Veículos jornalísticos** que cobrem esses eventos
- **Pesquisadores e ativistas** que inspiram este trabalho
- **Contribuidores** que ajudam a melhorar o sistema
- **Google** pelo acesso à API Gemini

---

## 💬 Contato

- **Desenvolvedor:** João Carabetta
- **Email:** joao.carabetta@gmail.com
- **GitHub:** [@JoaoCarabetta](https://github.com/JoaoCarabetta)
- **Repositório:** [arquivo-da-violencia](https://github.com/JoaoCarabetta/arquivo-da-violencia)

---

## ⚖️ Nota sobre Uso dos Dados

Os dados disponibilizados por este projeto são coletados de fontes públicas (notícias) e processados automaticamente. 

**Ao usar estes dados, você concorda em:**

1. **Verificar a fonte original** antes de publicar análises
2. **Citar este projeto** como fonte secundária
3. **Reconhecer as limitações** metodológicas
4. **Usar com responsabilidade** social e ética
5. **Não usar para fins discriminatórios** ou prejudiciais

---

<div align="center">

### 🌟 Se este projeto é útil para você, considere dar uma estrela!

**Juntos podemos ter dados mais transparentes e acessíveis sobre violência no Brasil.**

[![Star on GitHub](https://img.shields.io/github/stars/JoaoCarabetta/arquivo-da-violencia.svg?style=social)](https://github.com/JoaoCarabetta/arquivo-da-violencia/stargazers)

</div>
