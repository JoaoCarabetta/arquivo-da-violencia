import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { AlertTriangle, CheckCircle, Code, Database, Search, FileText, MapPin, GitBranch, Github } from 'lucide-react';
import { generateSEOTags } from '@/lib/seo';

export function About() {
  const seoTags = generateSEOTags({
    title: 'Sobre o Projeto',
    description: 'Conheça o Arquivo da Violência: um sistema automatizado de monitoramento de mortes violentas no Brasil. Entenda a metodologia, limitações e como contribuir.',
    path: '/sobre',
  });

  return (
    <div className="container mx-auto px-6 py-12 max-w-4xl">
      <div className="mb-8">
        <h1 className="text-4xl font-bold tracking-tight mb-2">Sobre o Projeto</h1>
        <p className="text-lg text-muted-foreground">
          Monitoramento em tempo real de mortes violentas no Brasil
        </p>
      </div>

      {/* Argumento */}
      <Card className="mb-8">
        <CardHeader>
          <CardTitle>O Problema</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4 text-sm leading-relaxed">
        <p>
          Em 2024 o Brasil registrou 35.365 homicídios.
          Só a grandeza do número já é absurda e deixa claro que segurança pública é um problema sério.
          Mesmo assim, a taxa de resolução de homicídios é pífia.
        </p>

        <p>
          Cada esfera do governo finge que resolve o problema separadamente.
          Dentro da polícia, não há colaboração real entre a Civil e a Militar.
          Nas cidades, a polícia estadual não colabora com a municipal.
          E a educação e a assistência social, a grande promessa de prevenção, não conseguem evitar que jovens se tornem vítimas de violência.
          Cada um por si, com sua própria agenda, “tentando” resolver o problema mais grave do país.
          O crime contra a vida não parece grave o suficiente para justificar um esforço de colaboração de verdade.
        </p>

        <p>
          Parece positivo termos os dados de homicídios de 2024.
          Mas é vergonhoso que essa informação só tenha sido divulgada em junho de 2025.
          Seis meses para compilar informações.
          Em seis meses, mais 15 mil pessoas morreram violentamente e a sociedade continua no escuro.
        </p>

        <p>
          E isso não acontece porque faltam tecnologias para coletar os dados.
          Nem porque esses dados não estejam registrados em lugar nenhum.
          A verdade é simples: todos os estados têm uma base com registros de boletins de ocorrência (BO).
          Esses bancos são atualizados diariamente por escrivães.
        </p>

        <p>
          Mas, aparentemente, o Brasil não consegue integrar 27 bases de BO para criar uma contagem de homicídios em tempo quase real.
          A gente não fez isso com a Covid?
          E me parece mais difícil identificar se alguém morreu de Covid do que de homicídio.
        </p>

        <p>
          O apagão de dados tem um motivo incômodo: falta interesse real em resolver o problema.
          É mais fácil acreditar em uniforme novo, operação aleatória e anúncio de ocasião.
          Só que o único jeito de reduzir mortes violentas é cooperando, encarando a complexidade das causas e atuando em todas as frentes.
        </p>

        <p>
          Para cooperar, precisamos saber o que está acontecendo.
          E precisamos saber com detalhe, rapidez e eficiência.
          Só assim dá pra medir se estamos sendo efetivos, ajustar políticas no meio do caminho e permitir que a sociedade cobre resultado.
        </p>

        <p>
          O Arquivo da Violência é uma demonstração de que dá, sim, para ter informações sobre crimes de forma detalhada e em tempo quase real.
          Essas histórias já recheiam jornais com pesar e desgosto.
          Na falta de dados oficiais, o Arquivo da Violência vai usar informações espalhadas nas redes sociais para construir uma base de homicídios em tempo real.
        </p>

        <p>
          A expectativa é que essa iniciativa sirva como ferramenta para sociedade civil, jornalistas, pesquisadores e formuladores de políticas públicas.
          E que deixe os responsáveis pela segurança pública do país desconfortáveis.
        </p>

        <p>
          A missão do Arquivo da Violência é ser substituído por uma ferramenta oficial, divulgada pelo governo federal, com dados de homicídios em tempo real.
          E os criadores do projeto também se dispõem a desenvolver essa ferramenta em um mês, desde que haja acesso às bases dos estados.
        </p>

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
          <div className="flex items-center gap-3 mb-4">
            <a
              href="https://github.com/JoaoCarabetta/arquivo-da-violencia"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 text-foreground hover:text-primary transition-colors"
            >
              <Github className="h-6 w-6" />
              <span className="font-medium">GitHub</span>
            </a>
          </div>
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

