import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Download, ExternalLink } from 'lucide-react';

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
          <CardTitle className="flex items-center gap-2">
            <Download className="h-5 w-5" />
            Download dos Dados
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground mb-6">
            Baixe todos os eventos únicos registrados em formato CSV ou abra os dados diretamente no Google Colab para análise interativa. Os dados incluem todos os campos disponíveis e são atualizados em tempo real.
          </p>
          <div className="grid gap-4 md:grid-cols-2">
            <a href="/api/public/events/export" download>
              <Button className="w-full" size="lg">
                <Download className="h-4 w-4 mr-2" />
                Download CSV Completo
              </Button>
            </a>
            <a 
              href="https://colab.research.google.com/github/JoaoCarabetta/arquivo-da-violencia/blob/master/notebooks/load_data.ipynb" 
              target="_blank" 
              rel="noopener noreferrer"
            >
              <Button className="w-full" size="lg" variant="outline">
                <ExternalLink className="h-4 w-4 mr-2" />
                Abrir no Google Colab
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
          <p className="text-sm text-muted-foreground mb-4">
            Todos os campos disponíveis no arquivo CSV de download:
          </p>
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
                  <td className="py-2 px-4 font-mono text-xs">homicide_type</td>
                  <td className="py-2 px-4">Tipo: Homicídio, Homicídio Qualificado, Tentativa de Homicídio, Outro</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">method_of_death</td>
                  <td className="py-2 px-4">Método (Arma de fogo, Arma branca, etc.)</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">event_date</td>
                  <td className="py-2 px-4">Data em que o evento ocorreu (ISO 8601)</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">date_precision</td>
                  <td className="py-2 px-4">Precisão da data (exato, aproximado, etc.)</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">time_of_day</td>
                  <td className="py-2 px-4">Período do dia (Manhã, Tarde, Noite, Madrugada)</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">country</td>
                  <td className="py-2 px-4">País (geralmente "Brasil")</td>
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
                  <td className="py-2 px-4 font-mono text-xs">street</td>
                  <td className="py-2 px-4">Rua ou logradouro</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">establishment</td>
                  <td className="py-2 px-4">Estabelecimento ou local específico</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">full_location_description</td>
                  <td className="py-2 px-4">Descrição completa da localização</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">latitude, longitude</td>
                  <td className="py-2 px-4">Coordenadas geográficas (quando disponível)</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">plus_code</td>
                  <td className="py-2 px-4">Código Plus do Google Maps</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">place_id</td>
                  <td className="py-2 px-4">ID do lugar no Google Maps</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">formatted_address</td>
                  <td className="py-2 px-4">Endereço formatado pelo Google Maps</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">location_precision</td>
                  <td className="py-2 px-4">Precisão da geolocalização (exato, aproximado, centro do bairro, centro da cidade)</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">geocoding_source</td>
                  <td className="py-2 px-4">Fonte da geocodificação (google_maps, manual, etc.)</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">geocoding_confidence</td>
                  <td className="py-2 px-4">Confiança da geocodificação (0.0 a 1.0)</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">victim_count</td>
                  <td className="py-2 px-4">Número total de vítimas fatais</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">identified_victim_count</td>
                  <td className="py-2 px-4">Número de vítimas identificadas</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">victims_summary</td>
                  <td className="py-2 px-4">Resumo das vítimas (nomes, idades, etc.)</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">perpetrator_count</td>
                  <td className="py-2 px-4">Número de perpetradores</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">identified_perpetrator_count</td>
                  <td className="py-2 px-4">Número de perpetradores identificados</td>
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
                  <td className="py-2 px-4">Descrição detalhada e cronológica do evento</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">additional_context</td>
                  <td className="py-2 px-4">Contexto adicional sobre o evento</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">merged_data</td>
                  <td className="py-2 px-4">Dados estruturados completos em formato JSON (string)</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">source_count</td>
                  <td className="py-2 px-4">Número de fontes jornalísticas que reportaram o evento</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">confirmed</td>
                  <td className="py-2 px-4">Status de confirmação manual (true/false)</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">needs_enrichment</td>
                  <td className="py-2 px-4">Se o evento precisa de enriquecimento (true/false)</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">last_enriched_at</td>
                  <td className="py-2 px-4">Data da última atualização de enriquecimento (ISO 8601)</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">enrichment_model</td>
                  <td className="py-2 px-4">Modelo de IA usado para enriquecimento</td>
                </tr>
                <tr className="border-b">
                  <td className="py-2 px-4 font-mono text-xs">created_at</td>
                  <td className="py-2 px-4">Data de registro no sistema (ISO 8601)</td>
                </tr>
                <tr>
                  <td className="py-2 px-4 font-mono text-xs">updated_at</td>
                  <td className="py-2 px-4">Data da última atualização (ISO 8601)</td>
                </tr>
              </tbody>
            </table>
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

