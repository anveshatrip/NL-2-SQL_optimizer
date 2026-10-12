import React, { useState, useEffect } from 'react';
import { 
  Database, Play, Sparkles, AlertTriangle, ArrowRight, CheckCircle2, 
  BarChart3, RefreshCw, Zap, Clock, DollarSign, Layers, Table2, ShieldAlert
} from 'lucide-react';

const API_BASE = 'http://localhost:8000';

export default function App() {
  const [nlQuery, setNlQuery] = useState('Show all orders placed by users from India with their total amount');
  const [provider, setProvider] = useState('gemini');
  const [simulateLarge, setSimulateLarge] = useState(true);
  
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('optimize'); // 'optimize' | 'compare' | 'schema'
  
  // Results
  const [optimizeData, setOptimizeData] = useState(null);
  const [compareData, setCompareData] = useState(null);
  const [schemaData, setSchemaData] = useState(null);
  const [error, setError] = useState(null);
  
  // Fetch Schema on mount
  useEffect(() => {
    fetchSchema();
  }, []);

  const fetchSchema = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/schema`);
      if (res.ok) {
        const data = await res.json();
        setSchemaData(data);
      }
    } catch (err) {
      console.warn('Backend not yet reachable for schema fetch:', err);
    }
  };

  const handleOptimize = async () => {
    if (!nlQuery.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/optimize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          nl_query: nlQuery,
          provider: provider,
          simulate_large: simulateLarge,
        }),
      });
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || `Server returned ${res.status}`);
      }
      const data = await res.json();
      setOptimizeData(data);
      setActiveTab('optimize');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCompare = async () => {
    if (!nlQuery.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/compare`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          nl_query: nlQuery,
          providers: ['gemini', 'openai', 'anthropic'],
        }),
      });
      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || `Server returned ${res.status}`);
      }
      const data = await res.json();
      setCompareData(data);
      setActiveTab('compare');
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const sampleQueries = [
    "Show all orders placed by users from India with their total amount",
    "List products in Electronics with average review rating above 4",
    "Find users who placed more than 3 orders with pending status",
    "Find all reviews written for products with price greater than 100"
  ];

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
      {/* Top Navbar */}
      <header className="border-b border-slate-800 bg-slate-900/60 backdrop-blur px-6 py-4 flex items-center justify-between sticky top-0 z-50">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-indigo-500/10 border border-indigo-500/20 rounded-xl text-indigo-400">
            <Sparkles className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-lg font-bold bg-gradient-to-r from-indigo-400 to-cyan-400 bg-clip-text text-transparent">
              NL2SQL Query Optimizer
            </h1>
            <p className="text-xs text-slate-400">Schema-Aware Translation with Automated EXPLAIN Feedback</p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button 
            onClick={() => setActiveTab('optimize')}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${activeTab === 'optimize' ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}`}>
            Optimizer Studio
          </button>
          <button 
            onClick={() => setActiveTab('compare')}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition ${activeTab === 'compare' ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}`}>
            Model Cost Comparison
          </button>
          <button 
            onClick={() => { setActiveTab('schema'); fetchSchema(); }}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition flex items-center gap-1.5 ${activeTab === 'schema' ? 'bg-indigo-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'}`}>
            <Database className="w-4 h-4" /> Schema Viewer
          </button>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 flex flex-col gap-6">
        {/* Input Card */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col gap-4">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <label className="text-sm font-semibold text-slate-300 flex items-center gap-2">
              <Zap className="w-4 h-4 text-cyan-400" />
              Enter Natural Language Query:
            </label>
            <div className="flex flex-wrap items-center gap-4 text-xs">
              <div className="flex items-center gap-2">
                <span className="text-slate-400">Provider:</span>
                <select 
                  value={provider} 
                  onChange={(e) => setProvider(e.target.value)}
                  className="bg-slate-800 border border-slate-700 rounded-lg px-2.5 py-1 text-slate-200 outline-none focus:border-indigo-500">
                  <option value="gemini">Gemini 2.0 Flash</option>
                  <option value="openai">OpenAI (GPT-4o Mini)</option>
                  <option value="anthropic">Anthropic (Claude 3.5 Haiku)</option>
                </select>
              </div>

              <label className="flex items-center gap-2 cursor-pointer text-slate-300 select-none">
                <input 
                  type="checkbox" 
                  checked={simulateLarge} 
                  onChange={(e) => setSimulateLarge(e.target.checked)}
                  className="rounded bg-slate-800 border-slate-700 text-indigo-600 focus:ring-0" 
                />
                Simulate Large-Scale Planner (enable_seqscan=OFF)
              </label>
            </div>
          </div>

          <div className="relative">
            <textarea
              rows={2}
              value={nlQuery}
              onChange={(e) => setNlQuery(e.target.value)}
              placeholder="e.g. Find all products ordered more than 5 times with price > 50..."
              className="w-full bg-slate-950 border border-slate-700 rounded-xl px-4 py-3 text-sm text-slate-100 placeholder:text-slate-500 focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 outline-none resize-none"
            />
          </div>

          {/* Quick Sample Queries */}
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-slate-500">Try Sample:</span>
            {sampleQueries.map((q, idx) => (
              <button 
                key={idx}
                onClick={() => setNlQuery(q)}
                className="bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 px-2.5 py-1 rounded-md transition text-left truncate max-w-xs">
                {q}
              </button>
            ))}
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-end gap-3 pt-2">
            <button
              onClick={handleCompare}
              disabled={loading}
              className="bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 px-4 py-2 rounded-xl text-sm font-semibold flex items-center gap-2 transition disabled:opacity-50">
              <BarChart3 className="w-4 h-4 text-cyan-400" />
              Compare Providers (Cost & Latency)
            </button>
            <button
              onClick={handleOptimize}
              disabled={loading}
              className="bg-gradient-to-r from-indigo-500 to-cyan-500 hover:from-indigo-600 hover:to-cyan-600 text-white px-5 py-2 rounded-xl text-sm font-semibold flex items-center gap-2 transition shadow-lg shadow-indigo-500/20 disabled:opacity-50">
              {loading ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
              Translate & Optimize Query
            </button>
          </div>
        </div>

        {error && (
          <div className="bg-rose-500/10 border border-rose-500/30 rounded-xl p-4 flex items-center gap-3 text-rose-300 text-sm">
            <ShieldAlert className="w-5 h-5 flex-shrink-0 text-rose-400" />
            <div>
              <p className="font-semibold">Query execution error</p>
              <p className="text-xs text-rose-300/80">{error}</p>
            </div>
          </div>
        )}

        {/* Tab 1: Full Optimizer Studio */}
        {activeTab === 'optimize' && optimizeData && (
          <div className="flex flex-col gap-6 animate-fade-in">
            {/* Top Stat Banner */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex items-center gap-4">
                <div className={`p-3 rounded-lg ${optimizeData.improved ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'}`}>
                  <BarChart3 className="w-6 h-6" />
                </div>
                <div>
                  <p className="text-xs text-slate-400 font-medium">Cost Reduction</p>
                  <p className="text-2xl font-bold text-slate-100">
                    {optimizeData.cost_reduction_pct > 0 ? `-${optimizeData.cost_reduction_pct}%` : `${optimizeData.cost_reduction_pct}%`}
                  </p>
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex items-center gap-4">
                <div className="p-3 bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 rounded-lg">
                  <Clock className="w-6 h-6" />
                </div>
                <div>
                  <p className="text-xs text-slate-400 font-medium">Execution Time</p>
                  <p className="text-2xl font-bold text-slate-100">
                    {optimizeData.original_plan.execution_time_ms}ms <span className="text-xs text-slate-400 font-normal">➔</span> {optimizeData.optimized_plan.execution_time_ms}ms
                  </p>
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex items-center gap-4">
                <div className="p-3 bg-rose-500/10 text-rose-400 border border-rose-500/20 rounded-lg">
                  <AlertTriangle className="w-6 h-6" />
                </div>
                <div>
                  <p className="text-xs text-slate-400 font-medium">Anti-Patterns Caught</p>
                  <p className="text-2xl font-bold text-slate-100">{optimizeData.antipattern_count}</p>
                </div>
              </div>

              <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 flex items-center gap-4">
                <div className="p-3 bg-purple-500/10 text-purple-400 border border-purple-500/20 rounded-lg">
                  <DollarSign className="w-6 h-6" />
                </div>
                <div>
                  <p className="text-xs text-slate-400 font-medium">LLM API Cost</p>
                  <p className="text-2xl font-bold text-slate-100">${optimizeData.total_llm_cost_usd.toFixed(6)}</p>
                </div>
              </div>
            </div>

            {/* Side by Side Queries */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Original SQL */}
              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 flex flex-col gap-3">
                <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-amber-400"></span>
                    <h2 className="text-sm font-semibold text-slate-200">1. Initial Generated SQL</h2>
                  </div>
                  <span className="text-xs px-2 py-0.5 rounded bg-amber-400/10 text-amber-300 border border-amber-400/20">
                    Planner Cost: {optimizeData.original_plan.total_cost}
                  </span>
                </div>
                <pre className="bg-slate-950 p-4 rounded-xl text-xs font-mono text-amber-200/90 overflow-x-auto border border-slate-800/80 leading-relaxed">
                  {optimizeData.original_sql}
                </pre>
                
                <div className="text-xs text-slate-400 flex items-center justify-between pt-1">
                  <span>Execution: <b>{optimizeData.original_plan.execution_time_ms} ms</b></span>
                  <span>Planning: <b>{optimizeData.original_plan.planning_time_ms} ms</b></span>
                  <span>Nodes: <b>{optimizeData.original_plan.node_types.join(', ')}</b></span>
                </div>
              </div>

              {/* Optimized SQL */}
              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 flex flex-col gap-3">
                <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
                    <h2 className="text-sm font-semibold text-slate-200">2. Optimized Query Rewrite</h2>
                  </div>
                  <span className="text-xs px-2 py-0.5 rounded bg-emerald-400/10 text-emerald-300 border border-emerald-400/20">
                    Planner Cost: {optimizeData.optimized_plan.total_cost}
                  </span>
                </div>
                <pre className="bg-slate-950 p-4 rounded-xl text-xs font-mono text-emerald-300 overflow-x-auto border border-slate-800/80 leading-relaxed">
                  {optimizeData.optimized_sql}
                </pre>
                
                <div className="text-xs text-slate-400 flex items-center justify-between pt-1">
                  <span>Execution: <b>{optimizeData.optimized_plan.execution_time_ms} ms</b></span>
                  <span>Planning: <b>{optimizeData.optimized_plan.planning_time_ms} ms</b></span>
                  <span>Nodes: <b>{optimizeData.optimized_plan.node_types.join(', ')}</b></span>
                </div>
              </div>
            </div>

            {/* Anti-Patterns Caught Box */}
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 flex flex-col gap-4">
              <h3 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-400" />
                Detected Performance Anti-Patterns ({optimizeData.antipattern_count})
              </h3>
              
              {optimizeData.antipatterns.length === 0 ? (
                <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-4 text-emerald-300 text-sm flex items-center gap-2">
                  <CheckCircle2 className="w-5 h-5" /> No major performance anti-patterns identified in original query.
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {optimizeData.antipatterns.map((ap, idx) => (
                    <div key={idx} className="bg-slate-950 border border-slate-800 rounded-xl p-4 flex flex-col gap-2">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-bold text-slate-200 flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${ap.severity === 'HIGH' ? 'bg-rose-500' : 'bg-amber-500'}`}></span>
                          {ap.title}
                        </span>
                        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded ${ap.severity === 'HIGH' ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30' : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'}`}>
                          {ap.severity}
                        </span>
                      </div>
                      {ap.table && (
                        <p className="text-xs text-indigo-400 font-medium">Table: {ap.table}</p>
                      )}
                      <p className="text-xs text-slate-400 leading-relaxed">{ap.description}</p>
                      <div className="bg-slate-900 p-2.5 rounded-lg border border-slate-800 text-xs text-cyan-300/90 font-mono mt-1">
                        💡 {ap.suggestion}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Tab 2: Provider Cost Comparison */}
        {activeTab === 'compare' && compareData && (
          <div className="flex flex-col gap-6 animate-fade-in">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-base font-bold text-slate-200">Multi-Model Cost & Latency Benchmark</h2>
                <p className="text-xs text-slate-400">Comparing translation of identical prompt across models</p>
              </div>
              <div className="flex items-center gap-4 text-xs font-medium">
                {compareData.cheapest_provider && (
                  <span className="px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    🏆 Lowest Cost: <b>{compareData.cheapest_provider.toUpperCase()}</b>
                  </span>
                )}
                {compareData.fastest_provider && (
                  <span className="px-3 py-1 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
                    ⚡ Fastest Response: <b>{compareData.fastest_provider.toUpperCase()}</b>
                  </span>
                )}
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              {compareData.results.map((res, idx) => (
                <div key={idx} className="bg-slate-900 border border-slate-800 rounded-2xl p-5 flex flex-col justify-between gap-4">
                  <div className="flex flex-col gap-3">
                    <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                      <div>
                        <h3 className="text-sm font-bold text-slate-100 capitalize">{res.provider}</h3>
                        <p className="text-[11px] text-slate-400 font-mono">{res.model}</p>
                      </div>
                      <span className={`text-[10px] px-2 py-0.5 rounded font-semibold ${res.error ? 'bg-rose-500/20 text-rose-300' : 'bg-indigo-500/20 text-indigo-300'}`}>
                        {res.error ? 'Unavailable' : 'Success'}
                      </span>
                    </div>

                    {res.error ? (
                      <p className="text-xs text-rose-400/80 bg-rose-500/10 p-3 rounded-lg border border-rose-500/20">
                        {res.error}
                      </p>
                    ) : (
                      <>
                        <div className="grid grid-cols-2 gap-2 text-xs">
                          <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800">
                            <span className="text-slate-500 block">API Cost:</span>
                            <span className="font-bold text-slate-200">${res.cost_usd.toFixed(6)}</span>
                          </div>
                          <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800">
                            <span className="text-slate-500 block">Latency:</span>
                            <span className="font-bold text-slate-200">{res.latency_ms} ms</span>
                          </div>
                          <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800">
                            <span className="text-slate-500 block">Tokens:</span>
                            <span className="font-bold text-slate-200">{res.total_tokens} total</span>
                          </div>
                          <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800">
                            <span className="text-slate-500 block">Output Len:</span>
                            <span className="font-bold text-slate-200">{res.output_tokens} tokens</span>
                          </div>
                        </div>

                        <div>
                          <p className="text-[11px] text-slate-400 mb-1 font-medium">Generated SQL:</p>
                          <pre className="bg-slate-950 p-3 rounded-xl text-[11px] font-mono text-cyan-200/90 overflow-x-auto border border-slate-800 max-h-48">
                            {res.sql}
                          </pre>
                        </div>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tab 3: Schema Viewer */}
        {activeTab === 'schema' && (
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 flex flex-col gap-6 animate-fade-in">
            <div className="flex items-center justify-between pb-4 border-b border-slate-800">
              <div>
                <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
                  <Database className="w-5 h-5 text-indigo-400" />
                  Live Introspected Relational Schema
                </h2>
                <p className="text-xs text-slate-400">Reflected dynamically via SQLAlchemy from live PostgreSQL</p>
              </div>
              <span className="text-xs px-3 py-1 bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 rounded-lg">
                {schemaData ? `${schemaData.table_count} Tables Found` : 'Loading...'}
              </span>
            </div>

            {schemaData ? (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                {Object.entries(schemaData.tables).map(([tableName, info]) => (
                  <div key={tableName} className="bg-slate-950 border border-slate-800 rounded-xl p-4 flex flex-col gap-3">
                    <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                      <span className="text-sm font-bold text-indigo-300 font-mono">
                        {tableName}
                      </span>
                      <span className="text-[11px] text-slate-500">
                        PK: {info.primary_key.join(', ') || 'none'}
                      </span>
                    </div>

                    <div className="flex flex-col gap-1.5 text-xs">
                      <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Columns:</p>
                      {info.columns.map((c, i) => (
                        <div key={i} className="flex justify-between text-slate-300 py-0.5 border-b border-slate-900">
                          <span className="font-mono text-slate-200">{c.name}</span>
                          <span className="text-slate-500 font-mono">{c.type}</span>
                        </div>
                      ))}
                    </div>

                    {info.foreign_keys.length > 0 && (
                      <div className="pt-2 text-xs">
                        <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Foreign Keys:</p>
                        {info.foreign_keys.map((fk, i) => (
                          <div key={i} className="text-amber-300/80 text-[11px] font-mono">
                            {fk.columns.join(', ')} ➔ {fk.references}
                          </div>
                        ))}
                      </div>
                    )}

                    <div className="pt-1 text-xs">
                      <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1">Indexes:</p>
                      <p className="text-slate-400 text-[11px] font-mono">
                        {info.indexes.length > 0 ? info.indexes.join(', ') : '(None - triggers Seq Scan)'}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="py-12 text-center text-slate-500 text-sm">
                Fetching database schema from backend...
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
