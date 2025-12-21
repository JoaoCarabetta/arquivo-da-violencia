import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Download, FileText, Code } from 'lucide-react';
import { getExportUrl } from '@/lib/api';

export function Data() {
  return (
    <div className="container mx-auto px-6 py-12 max-w-5xl">
      <div className="mb-8">
        <h1 className="text-4xl font-bold tracking-tight mb-2">Acesso aos Dados</h1>
        <p className="text-lg text-muted-foreground">
          Dados abertos para pesquisa, jornalismo e sociedade civil
        </p>
      </div>

      {/* Download Section */}
      <Card className="mb-8">
        <CardHeader>
          <CardTitle>Download dos Dados</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-6">
            Baixe todos os eventos registrados em formato CSV ou JSON. Os dados são atualizados em tempo real.
          </p>
          <div className="grid gap-4 md:grid-cols-2">
            <a href={getExportUrl('csv')} download>
              <Button className="w-full" size="lg">
                <Download className="h-4 w-4 mr-2" />
                Download CSV
              </Button>
            </a>
            <a href={getExportUrl('json')} download>
              <Button className="w-full" variant="outline" size="lg">
                <FileText className="h-4 w-4 mr-2" />
                Download JSON
              </Button>
            </a>
          </div>
        </CardContent>
      </Card>

      {/* Data Dictionary */}
      <Card className="mb-8">
        <CardHeader>
          <CardTitle>Dicionário de Dados</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b">
                  <th className="text-left py-2 px-4 font-medium">Campo</th>
                  <th className="text-left py-2 px-4 font-medium">Descrição</th>
                </tr>
              </thead>
              <tbody>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">id</td>
                  <td className="py-2 px-4">Identificador único do evento</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">event_date</td>
                  <td className="py-2 px-4">Data em que o evento ocorreu (ISO 8601)</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">time_of_day</td>
                  <td className="py-2 px-4">Período do dia (Manhã, Tarde, Noite, Madrugada)</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">state</td>
                  <td className="py-2 px-4">Sigla do estado (SP, RJ, etc.)</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">city</td>
                  <td className="py-2 px-4">Nome da cidade</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">neighborhood</td>
                  <td className="py-2 px-4">Bairro onde ocorreu</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">homicide_type</td>
                  <td className="py-2 px-4">Tipo: Homicídio, Homicídio Qualificado, Tentativa de Homicídio, Outro</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">method_of_death</td>
                  <td className="py-2 px-4">Método (Arma de fogo, Arma branca, etc.)</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">victim_count</td>
                  <td className="py-2 px-4">Número de vítimas fatais</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">security_force_involved</td>
                  <td className="py-2 px-4">Envolvimento de forças de segurança (true/false)</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">title</td>
                  <td className="py-2 px-4">Título resumido do evento</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">chronological_description</td>
                  <td className="py-2 px-4">Descrição detalhada e cronológica</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">latitude, longitude</td>
                  <td className="py-2 px-4">Coordenadas geográficas (quando disponível)</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">source_count</td>
                  <td className="py-2 px-4">Número de fontes jornalísticas</td>
                </tr>
                <tr>
                  <td className="py-2 px-4 font-mono text-xs">created_at</td>
                  <td className="py-2 px-4">Data de registro no sistema (ISO 8601)</td>
                </tr>
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* API Documentation */}
      <Card className="mb-8">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Code className="h-5 w-5" />
            API Pública
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-4">
            Acesse os dados programaticamente através da nossa API REST.
          </p>
          
          <div className="space-y-4">
            <div>
              <h4 className="font-mono text-sm font-medium mb-2">GET /api/public/stats</h4>
              <p className="text-sm text-muted-foreground mb-2">Estatísticas gerais</p>
              <pre className="bg-muted p-3 rounded text-xs overflow-x-auto">
{`curl https://arquivo.example.com/api/public/stats`}
              </pre>
            </div>

            <div>
              <h4 className="font-mono text-sm font-medium mb-2">GET /api/public/events</h4>
              <p className="text-sm text-muted-foreground mb-2">Lista paginada de eventos</p>
              <pre className="bg-muted p-3 rounded text-xs overflow-x-auto">
{`curl "https://arquivo.example.com/api/public/events?page=1&per_page=20&state=SP"`}
              </pre>
            </div>

            <div>
              <h4 className="font-mono text-sm font-medium mb-2">GET /api/public/stats/by-type</h4>
              <p className="text-sm text-muted-foreground mb-2">Contagem por tipo de morte</p>
              <pre className="bg-muted p-3 rounded text-xs overflow-x-auto">
{`curl https://arquivo.example.com/api/public/stats/by-type`}
              </pre>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Terms */}
      <Card>
        <CardHeader>
          <CardTitle>Termos de Uso</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-4 text-sm">
            <div>
              <h4 className="font-medium mb-1">Atribuição</h4>
              <p className="text-muted-foreground">
                Ao usar estes dados, por favor cite: "Arquivo da Violência" com link para este site.
              </p>
            </div>
            <div>
              <h4 className="font-medium mb-1">Licença</h4>
              <p className="text-muted-foreground">
                Os dados são disponibilizados como dados abertos para uso público.
              </p>
            </div>
            <div>
              <h4 className="font-medium mb-1">Limitações</h4>
              <p className="text-muted-foreground">
                Os dados são coletados automaticamente de fontes jornalísticas e podem conter erros ou omissões. 
                Veja a página "Sobre" para mais detalhes sobre a metodologia e limitações.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

