/**
 * Search Panel Component
 * 
 * Search documents in collection with results display
 */
import { useState } from 'react';
import { Search, Loader2, FileText } from 'lucide-react';
import { ragApi, SearchResult } from '../../api/rag.api';
import { useRagStore } from '../../stores/ragStore';
import clsx from 'clsx';

export default function SearchPanel() {
  const { currentCollectionId } = useRagStore();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isSearching, setIsSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  const handleSearch = async () => {
    if (!query.trim() || !currentCollectionId) return;

    setIsSearching(true);
    setHasSearched(true);

    try {
      const response = await ragApi.search(currentCollectionId, query.trim());
      setResults(response.results);
    } catch (error) {
      console.error('Search failed:', error);
      setResults([]);
    } finally {
      setIsSearching(false);
    }
  };

  return (
    <div className="border-t border-slate-700 bg-slate-800/30 p-4">
      {/* Search Input */}
      <div className="flex gap-2 mb-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
            placeholder="搜索文档内容..."
            disabled={!currentCollectionId}
            className={clsx(
              'w-full pl-10 pr-4 py-2.5 bg-slate-700/50 border border-slate-600 rounded-lg',
              'text-white placeholder-slate-400 text-sm',
              'focus:outline-none focus:ring-2 focus:ring-primary-500',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
          />
        </div>
        <button
          onClick={handleSearch}
          disabled={!query.trim() || !currentCollectionId || isSearching}
          className={clsx(
            'px-4 py-2.5 rounded-lg text-sm font-medium transition',
            query.trim() && currentCollectionId && !isSearching
              ? 'bg-primary-600 hover:bg-primary-700 text-white'
              : 'bg-slate-700 text-slate-500 cursor-not-allowed'
          )}
        >
          {isSearching ? <Loader2 className="w-4 h-4 animate-spin" /> : '搜索'}
        </button>
      </div>

      {/* Results */}
      {hasSearched && (
        <div className="space-y-2">
          {isSearching ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-primary-500" />
            </div>
          ) : results.length === 0 ? (
            <div className="text-center py-8">
              <Search className="w-8 h-8 text-slate-600 mx-auto mb-2" />
              <p className="text-sm text-slate-500">未找到相关内容</p>
            </div>
          ) : (
            <>
              <p className="text-xs text-slate-500 mb-2">
                找到 {results.length} 个相关片段
              </p>
              {results.map((result, index) => (
                <div
                  key={`${result.document_id}-${result.chunk_id}`}
                  className="p-3 bg-slate-800/50 rounded-lg border border-slate-700"
                >
                  <div className="flex items-center gap-2 mb-2">
                    <FileText className="w-4 h-4 text-slate-500" />
                    <span className="text-xs text-slate-400">
                      相关度: {(result.score * 100).toFixed(1)}%
                    </span>
                    <span className="text-xs text-slate-600">#{index + 1}</span>
                  </div>
                  <p className="text-sm text-slate-300 line-clamp-3">
                    {result.content}
                  </p>
                </div>
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}
