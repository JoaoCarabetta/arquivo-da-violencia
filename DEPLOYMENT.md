# Guia de Deploy

Este aplicativo suporta dois modos de deploy:

## 1. Modo Público (Public Mode)

Para deploy público, onde apenas a página de Incidentes é visível:

```bash
export PUBLIC_MODE=true
# ou no seu serviço de deploy (Heroku, Railway, etc.):
# PUBLIC_MODE=true
```

**O que fica visível:**
- ✅ Página de Incidentes (/)
- ✅ Detalhes de Incidentes (/incident/<id>)
- ✅ Página Sobre (/sobre)

**O que fica oculto:**
- ❌ Página de Fontes (/sources) - retorna 404
- ❌ Página de Eventos (/extractions) - retorna 404
- ❌ Links no menu de navegação para essas páginas são escondidos

## 2. Modo Desenvolvimento (Development Mode)

Para desenvolvimento local ou deploy interno:

```bash
export PUBLIC_MODE=false
# ou simplesmente não definir a variável
# PUBLIC_MODE não está definida
```

**O que fica visível:**
- ✅ Todas as páginas (Incidentes, Fontes, Eventos, Sobre)
- ✅ Todas as funcionalidades administrativas

## Exemplos de Uso

### Deploy Público (ex: Railway, Heroku, etc.)
```bash
# No painel de variáveis de ambiente do seu serviço:
PUBLIC_MODE=true
DATABASE_URL=sqlite:///instance/violence.db
```

### Desenvolvimento Local
```bash
# Não precisa definir PUBLIC_MODE (padrão é false)
uv run python run.py
```

### Teste Local em Modo Público
```bash
PUBLIC_MODE=true uv run python run.py
```
