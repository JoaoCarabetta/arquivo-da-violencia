import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import Editor from '@monaco-editor/react';
import { Panel, Group as PanelGroup, Separator as PanelResizeHandle } from 'react-resizable-panels';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card } from '@/components/ui/card';
import { 
  fetchRawEventById, 
  fetchSourceById, 
  updateRawEvent
} from '@/lib/api';
import { 
  ArrowLeft, 
  Save, 
  Star, 
  Loader2,
  AlertCircle,
  ExternalLink
} from 'lucide-react';

function formatDateTime(dateStr: string | null) {
  if (!dateStr) return null;
  return new Date(dateStr).toLocaleString('pt-BR', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'America/Sao_Paulo',
  });
}

export function RawEventDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  
  const [isGoldStandard, setIsGoldStandard] = useState(false);
  const [extractionJson, setExtractionJson] = useState('');
  const [isDirty, setIsDirty] = useState(false);
  const [jsonError, setJsonError] = useState<string | null>(null);

  // Fetch raw event
  const { data: event, isLoading: eventLoading, error: eventError } = useQuery({
    queryKey: ['raw-event', id],
    queryFn: () => fetchRawEventById(Number(id)),
    enabled: !!id,
  });

  // Fetch source content
  const { data: source, isLoading: sourceLoading } = useQuery({
    queryKey: ['source', event?.source_google_news_id],
    queryFn: () => fetchSourceById(event!.source_google_news_id!),
    enabled: !!event?.source_google_news_id,
  });

  // Initialize state when event loads
  useEffect(() => {
    if (event) {
      setIsGoldStandard(event.is_gold_standard);
      setExtractionJson(JSON.stringify(event.extraction_data, null, 2));
    }
  }, [event]);

  // Save mutation
  const saveMutation = useMutation({
    mutationFn: async () => {
      let parsedJson;
      try {
        parsedJson = JSON.parse(extractionJson);
      } catch (e) {
        throw new Error('Invalid JSON format');
      }

      return updateRawEvent(Number(id), {
        extraction_data: parsedJson,
        is_gold_standard: isGoldStandard,
      });
    },
    onSuccess: () => {
      setIsDirty(false);
      setJsonError(null);
      queryClient.invalidateQueries({ queryKey: ['raw-event', id] });
      queryClient.invalidateQueries({ queryKey: ['raw-events'] });
    },
    onError: (error: Error) => {
      setJsonError(error.message);
    },
  });

  const handleEditorChange = (value: string | undefined) => {
    if (value !== undefined) {
      setExtractionJson(value);
      setIsDirty(true);
      // Validate JSON
      try {
        JSON.parse(value);
        setJsonError(null);
      } catch (e) {
        setJsonError('Invalid JSON');
      }
    }
  };

  const handleGoldStandardToggle = () => {
    setIsGoldStandard(!isGoldStandard);
    setIsDirty(true);
  };

  const handleSave = () => {
    saveMutation.mutate();
  };

  if (eventLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (eventError || !event) {
    return (
      <div className="flex flex-col items-center justify-center h-screen gap-4">
        <AlertCircle className="h-12 w-12 text-destructive" />
        <p className="text-lg text-muted-foreground">
          Failed to load raw event. Event may not exist.
        </p>
        <Button onClick={() => navigate('/admin/raw-events')}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back to List
        </Button>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <div className="border-b bg-background px-6 py-4 flex items-center justify-between gap-4">
        <div className="flex items-center gap-4 min-w-0">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => navigate('/admin/raw-events')}
          >
            <ArrowLeft className="h-4 w-4 mr-2" />
            Back
          </Button>
          <div className="min-w-0">
            <h1 className="text-xl font-semibold truncate">
              Raw Event #{event.id}
            </h1>
            {event.title && (
              <p className="text-sm text-muted-foreground truncate">
                {event.title}
              </p>
            )}
          </div>
          <Badge 
            variant={event.extraction_success ? 'default' : 'destructive'}
            className="shrink-0"
          >
            {event.extraction_success ? 'Extracted' : 'Failed'}
          </Badge>
        </div>
        
        <div className="flex items-center gap-2 shrink-0">
          <Button
            variant={isGoldStandard ? 'default' : 'outline'}
            size="sm"
            onClick={handleGoldStandardToggle}
            className="gap-2"
          >
            <Star className={`h-4 w-4 ${isGoldStandard ? 'fill-current' : ''}`} />
            Gold Standard
          </Button>
          <Button
            onClick={handleSave}
            disabled={!isDirty || !!jsonError || saveMutation.isPending}
            size="sm"
            className="gap-2"
          >
            {saveMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Save className="h-4 w-4" />
            )}
            Save
          </Button>
        </div>
      </div>

      {/* Status Messages */}
      {jsonError && (
        <div className="px-6 py-2 bg-destructive/10 border-b border-destructive/20">
          <p className="text-sm text-destructive flex items-center gap-2">
            <AlertCircle className="h-4 w-4" />
            {jsonError}
          </p>
        </div>
      )}
      {saveMutation.isSuccess && !isDirty && (
        <div className="px-6 py-2 bg-green-50 dark:bg-green-950/30 border-b border-green-200 dark:border-green-900">
          <p className="text-sm text-green-700 dark:text-green-300">
            Changes saved successfully!
          </p>
        </div>
      )}

      {/* Split View */}
      <div className="flex-1 overflow-hidden">
        <PanelGroup orientation="horizontal">
          {/* Left Panel - Source Content */}
          <Panel defaultSize={40} minSize={25}>
            <div className="h-full flex flex-col bg-muted/30">
              <div className="px-4 py-3 border-b bg-background">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                  Raw Article Content
                </h2>
              </div>
              <div className="flex-1 overflow-auto p-4">
                {sourceLoading ? (
                  <div className="flex items-center justify-center h-32">
                    <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                  </div>
                ) : source ? (
                  <div className="space-y-4">
                    <Card className="p-4 space-y-3">
                      <div>
                        <dt className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">
                          Publisher
                        </dt>
                        <dd className="text-sm">{source.publisher_name || '—'}</dd>
                      </div>
                      <div>
                        <dt className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">
                          Published
                        </dt>
                        <dd className="text-sm">{formatDateTime(source.published_at)}</dd>
                      </div>
                      <div>
                        <dt className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-1">
                          URL
                        </dt>
                        <dd className="text-sm">
                          <a 
                            href={source.resolved_url || source.google_news_url || '#'}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-primary hover:underline inline-flex items-center gap-1"
                          >
                            View Article
                            <ExternalLink className="h-3 w-3" />
                          </a>
                        </dd>
                      </div>
                    </Card>
                    
                    <div>
                      <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wide mb-2">
                        Article Text
                      </h3>
                      <Card className="p-4">
                        <p className="text-sm leading-relaxed whitespace-pre-wrap">
                          {source.content || 'No content available'}
                        </p>
                      </Card>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-8 text-muted-foreground">
                    <p>No source content available</p>
                    <p className="text-xs mt-2">Source ID: {event.source_google_news_id || 'None'}</p>
                  </div>
                )}
              </div>
            </div>
          </Panel>

          {/* Resize Handle */}
          <PanelResizeHandle className="w-2 bg-border hover:bg-primary/20 transition-colors" />

          {/* Right Panel - JSON Editor */}
          <Panel defaultSize={60} minSize={25}>
            <div className="h-full flex flex-col bg-background">
              <div className="px-4 py-3 border-b">
                <h2 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                  Extracted JSON Data
                </h2>
              </div>
              <div className="flex-1 overflow-hidden">
                <Editor
                  height="100%"
                  defaultLanguage="json"
                  value={extractionJson}
                  onChange={handleEditorChange}
                  theme="vs-dark"
                  options={{
                    minimap: { enabled: true },
                    fontSize: 13,
                    lineNumbers: 'on',
                    scrollBeyondLastLine: false,
                    wordWrap: 'on',
                    formatOnPaste: true,
                    formatOnType: true,
                    automaticLayout: true,
                  }}
                />
              </div>
            </div>
          </Panel>
        </PanelGroup>
      </div>
    </div>
  );
}

