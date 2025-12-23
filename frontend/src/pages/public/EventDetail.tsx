import { useParams, Link, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { fetchPublicEventById, type PublicEvent } from '@/lib/api';
import {
  ArrowLeft,
  Calendar,
  Clock,
  MapPin,
  Users,
  Shield,
  ExternalLink,
  FileText,
  Loader2,
} from 'lucide-react';
import type { JSX } from 'react';

export function EventDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const eventId = id ? parseInt(id, 10) : null;

  const { data: event, isLoading, error } = useQuery({
    queryKey: ['public-event', eventId],
    queryFn: () => fetchPublicEventById(eventId!),
    enabled: !!eventId,
  });

  if (isLoading) {
    return (
      <div className="container mx-auto px-6 py-12 max-w-5xl">
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      </div>
    );
  }

  if (error || !event) {
    return (
      <div className="container mx-auto px-6 py-12 max-w-5xl">
        <Card>
          <CardContent className="pt-6">
            <div className="text-center py-8">
              <p className="text-lg font-medium mb-2">
                {error ? 'Erro ao carregar evento' : 'Evento não encontrado'}
              </p>
              <p className="text-sm text-muted-foreground mb-4">
                {error instanceof Error ? error.message : 'O evento solicitado não existe.'}
              </p>
              <Button asChild variant="outline">
                <Link to="/eventos">Voltar para Linha do Tempo</Link>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-6 py-12 max-w-5xl">
      {/* Header Section */}
      <div className="mb-6">
        <Button
          asChild
          variant="outline"
          className="mb-4 text-foreground"
        >
          <Link to="/eventos">
            <ArrowLeft className="h-4 w-4 mr-2" />
            Voltar para Linha do Tempo
          </Link>
        </Button>
        <h1 className="text-4xl font-bold mb-2">{event.title || 'Sem título'}</h1>
        {event.homicide_type && (
          <p className="text-lg text-muted-foreground">{event.homicide_type}</p>
        )}
      </div>

      {/* Main Content */}
      <div className="space-y-6">
        {/* Event Header Card */}
        <Card>
          <CardHeader>
            <CardTitle>{event.title || 'Detalhes do Evento'}</CardTitle>
          </CardHeader>
          <CardContent>
            {/* Badges Row */}
            <div className="flex gap-2 mb-4">
              {event.homicide_type && (
                <Badge variant="outline">{event.homicide_type}</Badge>
              )}
              {event.security_force_involved && (
                <Badge variant="destructive" className="gap-1">
                  <Shield className="h-3 w-3" />
                  Forças de Segurança
                </Badge>
              )}
            </div>

            {/* Metadata Grid */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              {event.event_date && (
                <div className="flex items-center gap-2">
                  <Calendar className="h-4 w-4 text-muted-foreground" />
                  <div>
                    {new Date(event.event_date).toLocaleDateString('pt-BR', {
                      day: '2-digit',
                      month: 'long',
                      year: 'numeric',
                    })}
                  </div>
                </div>
              )}
              {event.time_of_day && (
                <div className="flex items-center gap-2">
                  <Clock className="h-4 w-4 text-muted-foreground" />
                  <div>{event.time_of_day}</div>
                </div>
              )}
              {(event.city || event.state) && (
                <div className="flex items-center gap-2">
                  <MapPin className="h-4 w-4 text-muted-foreground" />
                  <div>
                    {[event.city, event.state].filter(Boolean).join(', ')}
                  </div>
                </div>
              )}
              {event.victim_count && (
                <div className="flex items-center gap-2">
                  <Users className="h-4 w-4 text-muted-foreground" />
                  <div>
                    {event.victim_count} {event.victim_count === 1 ? 'vítima' : 'vítimas'}
                  </div>
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Location Card */}
        {(event.latitude && event.longitude) || event.formatted_address ? (
          <Card>
            <CardHeader>
              <CardTitle>Localização</CardTitle>
            </CardHeader>
            <CardContent>
              {event.formatted_address && (
                <p className="text-sm mb-3">{event.formatted_address}</p>
              )}
              {event.latitude && event.longitude && (
                <Button asChild variant="outline">
                  <a
                    href={`https://www.google.com/maps?q=${event.latitude},${event.longitude}`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <MapPin className="h-4 w-4 mr-2" />
                    Ver no Google Maps
                    <ExternalLink className="h-4 w-4 ml-2" />
                  </a>
                </Button>
              )}
            </CardContent>
          </Card>
        ) : null}

        {/* Event Details Card */}
        {(event.method_of_death || event.security_force_involved) && (
          <Card>
            <CardHeader>
              <CardTitle>Detalhes do Evento</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              {event.method_of_death && (
                <div>
                  <div className="text-xs text-muted-foreground mb-1">Método</div>
                  <div className="font-medium">{event.method_of_death}</div>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Victims Information Card */}
        {(event.merged_data?.victims || event.victims_summary || event.victim_count) && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5" />
                Informações sobre as Vítimas
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="space-y-2">
                {(() => {
                  // Try to use merged_data.victims first (structured data)
                  const victimsData = event.merged_data?.victims;
                  const identifiableVictims = victimsData?.identifiable_victims;
                  const unidentifiedCount = victimsData?.number_of_unidentified_victims || 0;

                  const elements: JSX.Element[] = [];

                  // Show identifiable victims
                  if (
                    identifiableVictims &&
                    Array.isArray(identifiableVictims) &&
                    identifiableVictims.length > 0
                  ) {
                    identifiableVictims.forEach((victim: any, index: number) => {
                      const parts = [];
                      if (victim.name) parts.push(victim.name);
                      if (victim.age) parts.push(`${victim.age} anos`);
                      if (victim.gender) parts.push(victim.gender);
                      if (victim.occupation) parts.push(victim.occupation);

                      const victimText = parts.join(', ');
                      if (victimText) {
                        elements.push(
                          <div key={`identified-${index}`} className="flex items-start gap-2 text-sm">
                            <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary flex-shrink-0" />
                            <span className="leading-relaxed break-words flex-1">{victimText}</span>
                          </div>
                        );
                      }
                    });
                  }

                  // Show unidentified victims count
                  if (unidentifiedCount > 0) {
                    elements.push(
                      <div key="unidentified" className="flex items-start gap-2 text-sm text-muted-foreground">
                        <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-muted-foreground flex-shrink-0" />
                        <span className="leading-relaxed break-words flex-1 italic">
                          {unidentifiedCount}{' '}
                          {unidentifiedCount === 1
                            ? 'vítima não identificada'
                            : 'vítimas não identificadas'}
                        </span>
                      </div>
                    );
                  }

                  // If we have elements from merged_data, return them
                  if (elements.length > 0) {
                    return elements;
                  }

                  // Fallback to parsing victims_summary
                  if (event.victims_summary) {
                    const sentences = event.victims_summary.split('.');
                    const victimsText = sentences[0];
                    const victims = victimsText.split(/,(?![^()]*\))/);

                    return victims.map((victim, index) => {
                      const cleanedVictim = victim.replace(/^(e|and)\s+/i, '').trim();
                      if (!cleanedVictim) return null;

                      return (
                        <div key={index} className="flex items-start gap-2 text-sm">
                          <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary flex-shrink-0" />
                          <span className="leading-relaxed break-words flex-1">{cleanedVictim}</span>
                        </div>
                      );
                    });
                  }

                  // Final fallback - just show victim count if available
                  if (event.victim_count) {
                    return (
                      <div className="flex items-start gap-2 text-sm text-muted-foreground">
                        <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-muted-foreground flex-shrink-0" />
                        <span className="leading-relaxed break-words flex-1 italic">
                          {event.victim_count}{' '}
                          {event.victim_count === 1
                            ? 'vítima não identificada'
                            : 'vítimas não identificadas'}
                        </span>
                      </div>
                    );
                  }

                  return null;
                })()}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Description Card */}
        {event.chronological_description && (
          <Card>
            <CardHeader>
              <CardTitle>Descrição Cronológica</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm leading-relaxed whitespace-pre-wrap break-words">
                {event.chronological_description}
              </p>
            </CardContent>
          </Card>
        )}

        {/* Related News Card */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Notícias Relacionadas
            </CardTitle>
            {event.sources && event.sources.length > 0 && (
              <p className="text-sm text-muted-foreground">
                {event.sources.length} {event.sources.length === 1 ? 'fonte' : 'fontes'}
              </p>
            )}
          </CardHeader>
          <CardContent>
            {!event.sources || event.sources.length === 0 ? (
              <p className="text-muted-foreground text-sm text-center py-4">
                Nenhuma fonte disponível
              </p>
            ) : (
              <div className="space-y-0">
                {event.sources.map((source, index) => (
                  <div key={source.id}>
                    <div className="p-3 hover:bg-muted/50 rounded-lg transition-colors">
                      {source.url ? (
                        <a
                          href={source.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="flex items-start gap-2 group"
                        >
                          <ExternalLink className="h-4 w-4 text-muted-foreground group-hover:text-primary mt-0.5 flex-shrink-0" />
                          <div className="flex-1">
                            <div className="font-medium text-sm group-hover:text-primary group-hover:underline break-words">
                              {source.headline || source.publisher_name || 'Sem título'}
                            </div>
                            {(source.publisher_name || source.published_at) && (
                              <div className="flex items-center gap-2 text-xs text-muted-foreground ml-6 mt-1">
                                {source.publisher_name && <span>{source.publisher_name}</span>}
                                {source.publisher_name && source.published_at && <span>•</span>}
                                {source.published_at && (
                                  <span>
                                    {new Date(source.published_at).toLocaleDateString('pt-BR')}
                                  </span>
                                )}
                              </div>
                            )}
                          </div>
                        </a>
                      ) : (
                        <div className="flex items-start gap-2">
                          <div className="flex-1">
                            <div className="font-medium text-sm break-words">
                              {source.headline || source.publisher_name || 'Fonte sem título'}
                            </div>
                            {(source.publisher_name || source.published_at) && (
                              <div className="flex items-center gap-2 text-xs text-muted-foreground ml-6 mt-1">
                                {source.publisher_name && <span>{source.publisher_name}</span>}
                                {source.publisher_name && source.published_at && <span>•</span>}
                                {source.published_at && (
                                  <span>
                                    {new Date(source.published_at).toLocaleDateString('pt-BR')}
                                  </span>
                                )}
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                    {index < event.sources!.length - 1 && <Separator className="my-0" />}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}


