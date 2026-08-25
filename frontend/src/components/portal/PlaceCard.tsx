import { useNavigate } from 'react-router-dom';
import { useI18n } from '@/contexts/I18nContext';

export interface PlaceData {
  name: string;
  type: 'country' | 'state' | 'municipality';
  arquivoVictims: number;
  officialVictims?: number | null;
  officialAvailable: boolean;
  lastUpdated: string;
  period: 7 | 30 | 365;
  officialWindowStart?: string;
}

interface PlaceCardProps {
  placeData: PlaceData;
}

function formatTimeAgo(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);
  
  if (diffMins < 1) return 'agora mesmo';
  if (diffMins < 60) return `há ${diffMins} minuto${diffMins > 1 ? 's' : ''}`;
  if (diffHours < 24) return `há ${diffHours} hora${diffHours > 1 ? 's' : ''}`;
  if (diffDays < 30) return `há ${diffDays} dia${diffDays > 1 ? 's' : ''}`;
  return date.toLocaleDateString('pt-BR');
}

export function PlaceCard({ placeData }: PlaceCardProps) {
  const { t } = useI18n();
  const navigate = useNavigate();
  
  const periodLabels = {
    7: 'Últimos 7 dias',
    30: 'Últimos 30 dias',
    365: 'Último ano',
  };
  
  const lastUpdateFormatted = formatTimeAgo(placeData.lastUpdated);

  return (
    <div data-testid="place-card" className="rounded-xl border border-stone-200 bg-white p-6 space-y-6">
      {/* Place Name */}
      <div>
        <h2 className="text-2xl font-bold text-stone-900">{placeData.name}</h2>
        <p className="text-sm text-stone-500 mt-1">
          {placeData.type === 'country' && 'País'}
          {placeData.type === 'state' && 'Estado'}
          {placeData.type === 'municipality' && 'Município'}
        </p>
      </div>

      {/* Arquivo Count - Large */}
      <div>
        <div className="text-sm text-stone-500 mb-1">
          Vítimas (Arquivo da Violência)
        </div>
        <div data-testid="arquivo-count" className="text-5xl font-bold text-blue-600 mb-2">
          {placeData.arquivoVictims.toLocaleString('pt-BR')}
        </div>
        <div className="text-sm text-stone-600">
          {periodLabels[placeData.period]} · Última atualização {lastUpdateFormatted}
        </div>
      </div>

      {/* Official Count - Smaller */}
      {placeData.officialAvailable && placeData.officialVictims != null ? (
        <div className="border-t border-stone-200 pt-4">
          <div className="text-sm text-stone-500 mb-1">
            Vítimas (Oficial)
          </div>
          <div data-testid="official-count" className="text-3xl font-semibold text-stone-700 mb-2">
            {placeData.officialVictims.toLocaleString('pt-BR')}
          </div>
          <div className="text-xs text-stone-500">
            Ministério da Justiça e Segurança Pública, Formulário 1
            {placeData.officialWindowStart && ` (desde ${placeData.officialWindowStart})`}
          </div>
        </div>
      ) : (
        <div className="border-t border-stone-200 pt-4">
          <div className="text-sm text-stone-500 mb-1">
            Vítimas (Oficial)
          </div>
          <div className="text-sm text-stone-600 italic">
            Dados oficiais não publicados neste período
          </div>
        </div>
      )}

      {/* Counts are not the same sentence */}
      <div className="border-t border-stone-200 pt-4">
        <p className="text-sm text-stone-700">
          As contagens não são iguais devido a diferentes metodologias de coleta e janelas temporais.
        </p>
      </div>

      {/* Methodology Link */}
      <div>
        <a
          href="/metodologia"
          onClick={(e) => {
            e.preventDefault();
            navigate('/metodologia');
          }}
          className="text-sm text-blue-600 hover:text-blue-700 font-medium underline"
        >
          Como contamos
        </a>
      </div>

      {/* Scope Line */}
      {placeData.type === 'country' && placeData.name === 'Brasil' && (
        <div className="border-t border-stone-200 pt-4">
          <p className="text-xs text-stone-500">
            Busca em notícias cobre 52 capitais e grandes regiões metropolitanas do Brasil.
            Não cobre os 5.563 municípios nem apenas 63 cidades.
          </p>
        </div>
      )}
    </div>
  );
}
