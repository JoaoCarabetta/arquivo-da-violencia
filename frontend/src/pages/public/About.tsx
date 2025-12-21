import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { AlertTriangle, CheckCircle, Code, Database, Search, FileText, MapPin, GitBranch } from 'lucide-react';

export function About() {
  return (
    <div className="container mx-auto px-6 py-12 max-w-4xl">
      <div className="mb-8">
        <h1 className="text-4xl font-bold tracking-tight mb-2">Sobre o Projeto</h1>
        <p className="text-lg text-muted-foreground">
          Monitoramento em tempo real de mortes violentas no Brasil
        </p>
      </div>

      {/* O Problema */}
      <Card className="mb-8">
        <CardHeader>
          <CardTitle>O Problema</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm leading-relaxed">
          <p>
            O Brasil registra aproximadamente <strong>50.000 mortes violentas por ano</strong>, 
            tornando a violência letal um dos maiores problemas de saúde pública do país.
          </p>
          <p>
            No entanto, os dados oficiais (DataSUS, Fórum Brasileiro de Segurança Pública) são 
            divulgados apenas anualmente, com atrasos de meses ou até anos. Essa falta de dados 
            em tempo real dificulta:
          </p>
          <ul className="list-disc list-inside space-y-1 ml-4">
            <li>Resposta rápida de políticas públicas</li>
            <li>Alocação eficiente de recursos de segurança</li>
            <li>Cobertura jornalística informada</li>
            <li>Pesquisa acadêmica atualizada</li>
            <li>Conscientização pública sobre a dimensão do problema</li>
          </ul>
        </CardContent>
      </Card>

      {/* A Solução */}
      <Card className="mb-8">
        <CardHeader>
          <CardTitle>A Solução</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm leading-relaxed">
          <p>
            O <strong>Arquivo da Violência</strong> é uma iniciativa de código aberto que coleta 
            e estrutura dados sobre mortes violentas em tempo real, usando:
          </p>
          <ul className="list-disc list-inside space-y-1 ml-4">
            <li>Monitoramento automatizado de fontes jornalísticas</li>
            <li>Inteligência artificial para extração de dados estruturados</li>
            <li>Dados abertos e acessíveis para todos</li>
          </ul>
          <p>
            Os dados são disponibilizados gratuitamente para pesquisadores, jornalistas, 
            organizações da sociedade civil e formuladores de políticas públicas.
          </p>
        </CardContent>
      </Card>

      {/* Como Funciona */}
      <Card className="mb-8">
        <CardHeader>
          <CardTitle>Como Funciona</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-6">
            <div className="flex gap-4">
              <div className="flex-shrink-0">
                <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                  <Search className="h-5 w-5 text-primary" />
                </div>
              </div>
              <div>
                <h4 className="font-medium mb-1">1. Monitoramento</h4>
                <p className="text-sm text-muted-foreground">
                  Sistema monitora feeds RSS do Google News a cada hora, buscando notícias 
                  sobre mortes violentas.
                </p>
              </div>
            </div>

            <div className="flex gap-4">
              <div className="flex-shrink-0">
                <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                  <CheckCircle className="h-5 w-5 text-primary" />
                </div>
              </div>
              <div>
                <h4 className="font-medium mb-1">2. Classificação</h4>
                <p className="text-sm text-muted-foreground">
                  LLM (Google Gemini) analisa manchetes e identifica notícias sobre mortes violentas.
                </p>
              </div>
            </div>

            <div className="flex gap-4">
              <div className="flex-shrink-0">
                <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                  <FileText className="h-5 w-5 text-primary" />
                </div>
              </div>
              <div>
                <h4 className="font-medium mb-1">3. Download</h4>
                <p className="text-sm text-muted-foreground">
                  Conteúdo completo dos artigos é extraído usando trafilatura.
                </p>
              </div>
            </div>

            <div className="flex gap-4">
              <div className="flex-shrink-0">
                <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                  <Database className="h-5 w-5 text-primary" />
                </div>
              </div>
              <div>
                <h4 className="font-medium mb-1">4. Extração</h4>
                <p className="text-sm text-muted-foreground">
                  LLM extrai dados estruturados: data, local, tipo de morte, vítimas, método, etc.
                </p>
              </div>
            </div>

            <div className="flex gap-4">
              <div className="flex-shrink-0">
                <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                  <GitBranch className="h-5 w-5 text-primary" />
                </div>
              </div>
              <div>
                <h4 className="font-medium mb-1">5. Deduplicação</h4>
                <p className="text-sm text-muted-foreground">
                  Eventos duplicados (mesmo caso em múltiplas fontes) são consolidados.
                </p>
              </div>
            </div>

            <div className="flex gap-4">
              <div className="flex-shrink-0">
                <div className="w-10 h-10 rounded-full bg-primary/10 flex items-center justify-center">
                  <MapPin className="h-5 w-5 text-primary" />
                </div>
              </div>
              <div>
                <h4 className="font-medium mb-1">6. Geolocalização</h4>
                <p className="text-sm text-muted-foreground">
                  Coordenadas geográficas são obtidas via Google Maps Geocoding API.
                </p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Limitações */}
      <Card className="mb-8 border-amber-200 bg-amber-50 dark:bg-amber-950/20 dark:border-amber-900">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-amber-900 dark:text-amber-100">
            <AlertTriangle className="h-5 w-5" />
            Limitações Importantes
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div>
            <h4 className="font-medium mb-1">Cobertura Incompleta</h4>
            <p className="text-muted-foreground">
              Apenas mortes noticiadas pela mídia são capturadas. Muitas mortes, especialmente 
              em áreas com menos cobertura jornalística, não aparecem nos dados.
            </p>
          </div>
          <div>
            <h4 className="font-medium mb-1">Viés Regional</h4>
            <p className="text-muted-foreground">
              Regiões com mais veículos de imprensa terão mais eventos registrados, não 
              necessariamente mais mortes.
            </p>
          </div>
          <div>
            <h4 className="font-medium mb-1">Precisão dos Dados</h4>
            <p className="text-muted-foreground">
              Dados são extraídos automaticamente por IA e podem conter erros. Informações 
              como número exato de vítimas ou localização precisa podem estar incorretas.
            </p>
          </div>
          <div>
            <h4 className="font-medium mb-1">Possíveis Duplicações</h4>
            <p className="text-muted-foreground">
              Apesar do processo de deduplicação, alguns eventos podem estar duplicados se 
              noticiados de formas muito diferentes.
            </p>
          </div>
          <div>
            <h4 className="font-medium mb-1">Atraso</h4>
            <p className="text-muted-foreground">
              Eventos aparecem após publicação na mídia, com atraso de minutos a horas.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Categorias */}
      <Card className="mb-8">
        <CardHeader>
          <CardTitle>Categorias de Morte</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div>
            <h4 className="font-medium">Homicídio</h4>
            <p className="text-muted-foreground">
              Morte causada intencionalmente por outra pessoa.
            </p>
          </div>
          <div>
            <h4 className="font-medium">Homicídio Qualificado</h4>
            <p className="text-muted-foreground">
              Homicídio com agravantes (premeditado, contra vulnerável, por motivo torpe, etc.).
            </p>
          </div>
          <div>
            <h4 className="font-medium">Tentativa de Homicídio</h4>
            <p className="text-muted-foreground">
              Tentativa de assassinato onde a vítima sobreviveu.
            </p>
          </div>
          <div>
            <h4 className="font-medium">Outro</h4>
            <p className="text-muted-foreground">
              Mortes que não se encaixam nas categorias acima.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Tecnologia */}
      <Card className="mb-8">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Code className="h-5 w-5" />
            Tecnologia
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div>
            <h4 className="font-medium mb-1">Código Aberto</h4>
            <p className="text-muted-foreground">
              Todo o código está disponível no{' '}
              <a 
                href="https://github.com/JoaoCarabetta/arquivo-da-violencia"
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline"
              >
                GitHub
              </a>
              {' '}sob licença open source.
            </p>
          </div>
          <div>
            <h4 className="font-medium mb-1">Stack</h4>
            <p className="text-muted-foreground">
              Backend: Python, FastAPI, SQLite<br />
              Frontend: React, TypeScript, Vite<br />
              LLM: Google Gemini para classificação e extração<br />
              Geolocalização: Google Maps Geocoding API
            </p>
          </div>
          <div>
            <h4 className="font-medium mb-1">Atualização</h4>
            <p className="text-muted-foreground">
              O sistema coleta novos dados a cada hora, 24/7.
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Contribua */}
      <Card>
        <CardHeader>
          <CardTitle>Como Contribuir</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm">
          <p>
            Este é um projeto comunitário e sua contribuição é bem-vinda:
          </p>
          <ul className="list-disc list-inside space-y-1 ml-4">
            <li>
              Contribua com código no{' '}
              <a 
                href="https://github.com/JoaoCarabetta/arquivo-da-violencia"
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline"
              >
                GitHub
              </a>
            </li>
            <li>Reporte erros ou problemas nos dados</li>
            <li>Sugira melhorias na metodologia</li>
            <li>Compartilhe o projeto com pesquisadores e jornalistas</li>
            <li>Use os dados em suas pesquisas e reportagens</li>
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

