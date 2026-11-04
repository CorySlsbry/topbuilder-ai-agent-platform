"use client";

import { useCallback, useEffect, useState } from "react";

import { Kpi, Panel, Spark, Spinner } from "@/components/ui";
import { apiGetOrNull, apiRequest } from "@/lib/api";

// ---------------------------------------------------------------------------
// SEO & Content agent (#8) — weekly competitor gaps, GEO scorecard, blog queue,
// and comment drafts. Inline response types; fetch + friendly errors come from
// lib/api.ts. Drafts only — you approve before anything posts.
// ---------------------------------------------------------------------------

type CompetitorGap = {
  competitor: string;
  domain: string;
  domain_rating: number;
  keywords_we_miss: number;
  ai_citation_share: number;
  notes: string;
};

type GeoPageAudit = {
  page: string;
  url: string;
  word_count: number;
  facts_per_200_words: number;
  faq_count: number;
  freshness_days: number;
  score: number;
  status: string;
  fixes: string[];
};

type BlogOpportunity = {
  keyword: string;
  monthly_searches: number;
  difficulty: number;
  source: string;
  source_detail: string;
  intent: string;
  opportunity_score: number;
  outline: string[];
  draft_intro: string;
};

type CommentOpportunity = {
  platform: string;
  thread_title: string;
  url: string;
  relevance_score: number;
  draft_comment: string;
};

type WeeklySummary = {
  gaps_found: number;
  pages_below_benchmark: number;
  posts_planned: number;
  comments_drafted: number;
};

type SeoRunResult = {
  competitor_gaps: CompetitorGap[];
  geo_audit: GeoPageAudit[];
  blog_opportunities: BlogOpportunity[];
  comment_opportunities: CommentOpportunity[];
  weekly_summary: WeeklySummary;
  narration: string;
};

const getLatestSeoRun = (token: string) =>
  apiGetOrNull<SeoRunResult>(token, "/v1/agents/seo/runs/latest", "load the SEO report");

const runSeoAnalysis = (token: string) =>
  apiRequest<SeoRunResult>(token, "/v1/agents/seo/runs", "run the SEO agent", { method: "POST" });

// ---- formatting (rates/scores may arrive as 0–1 fractions or 0–100) ----

const toPts = (v: number) => (v <= 1 ? v * 100 : v);
const pct = (v: number) => `${Math.round(toPts(v))}%`;
const score = (v: number) => Math.round(toPts(v));
const fmt1 = (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(1));

function ScoreBar({ value }: { value: number }) {
  const v = Math.max(0, Math.min(100, score(value)));
  const bar = v >= 80 ? "bg-emerald-400" : v >= 60 ? "bg-amber-400" : "bg-red-400";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 overflow-hidden rounded-full bg-white/10">
        <div className={`h-full rounded-full ${bar}`} style={{ width: `${v}%` }} />
      </div>
      <span className="num text-xs text-zinc-400">{v}</span>
    </div>
  );
}

const SOURCE_COLORS: Record<string, string> = {
  reddit: "text-orange-300 bg-orange-300/10 border-orange-300/20",
  youtube: "text-red-300 bg-red-300/10 border-red-300/20",
  search: "text-[#7ea2ff] bg-[#7ea2ff]/10 border-[#7ea2ff]/20",
  google: "text-[#7ea2ff] bg-[#7ea2ff]/10 border-[#7ea2ff]/20",
  facebook: "text-[#7ea2ff] bg-[#7ea2ff]/10 border-[#7ea2ff]/20",
  linkedin: "text-sky-300 bg-sky-300/10 border-sky-300/20",
};

function SourceBadge({ value }: { value: string }) {
  const cls = SOURCE_COLORS[value.toLowerCase()] ?? "text-zinc-300 bg-white/5 border-white/10";
  return (
    <span className={`inline-flex rounded-md border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${cls}`}>
      {value}
    </span>
  );
}

function GeoStatus({ value }: { value: string }) {
  const pass = /pass|ok|good|healthy/i.test(value);
  const cls = pass
    ? "text-emerald-300 bg-emerald-300/10 border-emerald-300/20"
    : "text-amber-300 bg-amber-300/10 border-amber-300/20";
  return (
    <span className={`inline-flex rounded-md border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ${cls}`}>
      {value.replace(/_/g, " ")}
    </span>
  );
}

function PipelineRow({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-baseline justify-between">
      <span className="text-xs text-zinc-400">{label}</span>
      <span className="num text-sm font-medium text-zinc-100">{value}</span>
    </div>
  );
}

export default function SeoView({ token }: { token: string }) {
  const [data, setData] = useState<SeoRunResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getLatestSeoRun(token));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Load failed");
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    void load();
  }, [load]);

  async function run() {
    setRunning(true);
    setError(null);
    try {
      setData(await runSeoAnalysis(token));
    } catch (e) {
      setError(e instanceof Error ? e.message : "SEO run failed");
    } finally {
      setRunning(false);
    }
  }

  function toggle(id: string) {
    setOpen((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  if (loading) {
    return (
      <div className="panel grid place-items-center px-6 py-20 text-zinc-500">
        <Spinner />
        <span className="mt-3 text-sm">Loading SEO &amp; content…</span>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="space-y-4">
        {error && (
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>
        )}
        <div className="panel grid place-items-center px-6 py-16 text-center">
          <div className="grid h-12 w-12 place-items-center rounded-2xl bg-accent/15 text-accent ring-1 ring-accent/30">
            <Spark />
          </div>
          <h2 className="mt-4 text-lg font-semibold text-zinc-100">No weekly analysis yet</h2>
          <p className="mt-1 max-w-sm text-sm text-zinc-500">
            Competitor gaps, GEO page scores, a ranked blog queue, and comment drafts in your voice — refreshed weekly.
            Drafts only; you approve before anything posts.
          </p>
          <button className="btn-primary mt-5" onClick={run} disabled={running}>
            {running ? <Spinner /> : <Spark />}
            {running ? "Analyzing…" : "Run weekly analysis"}
          </button>
        </div>
      </div>
    );
  }

  const s = data.weekly_summary;
  const blog = [...data.blog_opportunities].sort((a, b) => b.opportunity_score - a.opportunity_score);
  const top = blog[0];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="text-xs text-zinc-500">
          Advisory content engine — everything below is a draft. You approve before anything posts.
        </span>
        <button className="btn-primary" onClick={run} disabled={running}>
          {running ? <Spinner /> : <Spark />}
          {running ? "Analyzing…" : "Run weekly analysis"}
        </button>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">{error}</div>
      )}

      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Kpi label="Competitor gaps" value={String(s.gaps_found)} tone="info" />
        <Kpi label="Pages below benchmark" value={String(s.pages_below_benchmark)} tone="warn" />
        <Kpi label="Posts planned" value={String(s.posts_planned)} tone="ok" />
        <Kpi label="Comments drafted" value={String(s.comments_drafted)} tone="neutral" />
      </section>

      <section className="grid grid-cols-1 gap-6 lg:grid-cols-5">
        <div className="panel p-5 lg:col-span-3">
          <h2 className="mb-2 text-sm font-semibold text-zinc-100">This week&apos;s plan</h2>
          <p className="label mb-3">deterministic audit · narration only explains</p>
          <div className="max-h-[300px] overflow-auto whitespace-pre-wrap text-[13px] leading-relaxed text-zinc-300">
            {data.narration}
          </div>
        </div>
        <div className="panel p-5 lg:col-span-2">
          <h2 className="mb-4 text-sm font-semibold text-zinc-100">Content pipeline</h2>
          <div className="space-y-3">
            <PipelineRow label="Blog posts queued" value={s.posts_planned} />
            <PipelineRow label="Comments drafted" value={s.comments_drafted} />
            <PipelineRow label="Pages to fix" value={s.pages_below_benchmark} />
          </div>
          <div className="mt-5 rounded-xl border border-accent/20 bg-accent/[0.07] px-4 py-3">
            <div className="text-xs text-zinc-400">Top opportunity this week</div>
            <div className="mt-1 truncate text-lg font-semibold tracking-tight text-accent-soft">
              {top ? top.keyword : "—"}
            </div>
            {top && (
              <div className="num mt-1 text-[11px] text-zinc-500">
                score {score(top.opportunity_score)} · {top.monthly_searches.toLocaleString("en-US")} searches/mo · via{" "}
                {top.source}
              </div>
            )}
          </div>
        </div>
      </section>

      <Panel title="Competitor gap analysis" aside={`${data.competitor_gaps.length} competitors tracked`}>
        {data.competitor_gaps.length === 0 ? (
          <p className="px-5 py-6 text-sm text-zinc-500">No competitor gaps found this week.</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="label border-b border-white/[0.06] text-left [&>th]:px-5 [&>th]:py-2.5">
                <th>Competitor</th><th className="text-right">DR</th>
                <th className="text-right">Keywords we miss</th>
                <th className="text-right">AI citation share</th><th>Notes</th>
              </tr>
            </thead>
            <tbody>
              {data.competitor_gaps.map((g) => (
                <tr key={g.domain} className="border-b border-white/[0.04] last:border-0 [&>td]:px-5 [&>td]:py-3">
                  <td>
                    <span className="font-medium text-zinc-100">{g.competitor}</span>
                    <span className="num ml-2 text-xs text-zinc-600">{g.domain}</span>
                  </td>
                  <td className="num text-right text-zinc-300">{g.domain_rating}</td>
                  <td className="num text-right font-medium text-amber-300">{g.keywords_we_miss}</td>
                  <td className="num text-right text-zinc-300">{pct(g.ai_citation_share)}</td>
                  <td className="text-zinc-500">{g.notes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>

      <Panel title="GEO scorecard — your pages vs. the citation benchmark" aside={`${data.geo_audit.length} pages audited`}>
        {data.geo_audit.length === 0 ? (
          <p className="px-5 py-6 text-sm text-zinc-500">No pages audited in this run.</p>
        ) : (
          <ul className="divide-y divide-white/[0.04]">
            {data.geo_audit.map((p) => (
              <li key={p.url} className="px-5 py-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="min-w-0">
                    <span className="text-sm font-medium text-zinc-100">{p.page}</span>
                    <span className="num ml-2 text-xs text-zinc-600">{p.url}</span>
                  </div>
                  <div className="flex shrink-0 items-center gap-3">
                    <ScoreBar value={p.score} />
                    <GeoStatus value={p.status} />
                  </div>
                </div>
                <div className="num mt-1.5 text-[11px] text-zinc-500">
                  {p.word_count.toLocaleString("en-US")} words · {fmt1(p.facts_per_200_words)} facts/200w ·{" "}
                  {p.faq_count} FAQs · updated {p.freshness_days}d ago
                </div>
                {p.fixes.length > 0 && (
                  <ul className="mt-2 space-y-1">
                    {p.fixes.map((f, i) => (
                      <li key={i} className="flex items-start gap-2 text-[13px] text-amber-300">
                        <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-amber-300/70" />
                        {f}
                      </li>
                    ))}
                  </ul>
                )}
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel title="Blog queue — drafts, you approve before anything posts" aside={`${blog.length} opportunities · sorted by score`}>
        {blog.length === 0 ? (
          <p className="px-5 py-6 text-sm text-zinc-500">No blog opportunities surfaced this week.</p>
        ) : (
          <ul className="divide-y divide-white/[0.04]">
            {blog.map((o) => {
              const id = `blog:${o.keyword}`;
              const expanded = open.has(id);
              return (
                <li key={o.keyword} className="px-5 py-3">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-medium text-zinc-100">{o.keyword}</span>
                        <SourceBadge value={o.source} />
                      </div>
                      <div className="num mt-1 text-[11px] text-zinc-500">
                        {o.monthly_searches.toLocaleString("en-US")} searches/mo · difficulty {o.difficulty} ·{" "}
                        {o.intent} · via {o.source_detail}
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-3">
                      <span className="num rounded-md border border-accent/25 bg-accent/10 px-1.5 py-0.5 text-[11px] font-medium text-accent-soft">
                        {score(o.opportunity_score)}
                      </span>
                      <button
                        className="btn-ghost !px-3 !py-1 text-xs"
                        onClick={() => toggle(id)}
                        aria-expanded={expanded}
                      >
                        {expanded ? "Hide outline" : "View outline"}
                      </button>
                    </div>
                  </div>
                  {expanded && (
                    <div className="mt-3 rounded-xl border border-accent/20 bg-accent/[0.05] px-4 py-3">
                      <div className="label mb-2">proposed outline</div>
                      <ol className="list-decimal space-y-1 pl-5 text-[13px] text-zinc-300">
                        {o.outline.map((step, i) => (
                          <li key={i}>{step}</li>
                        ))}
                      </ol>
                      <div className="label mb-1 mt-3">draft intro</div>
                      <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-zinc-300">{o.draft_intro}</p>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Panel>

      <Panel
        title="Comments in your voice"
        aside={`${data.comment_opportunities.length} drafts · posted only on approval`}
      >
        {data.comment_opportunities.length === 0 ? (
          <p className="px-5 py-6 text-sm text-zinc-500">No comment-worthy threads found this week.</p>
        ) : (
          <ul className="divide-y divide-white/[0.04]">
            {data.comment_opportunities.map((c) => {
              const id = `comment:${c.url}`;
              const expanded = open.has(id);
              return (
                <li key={c.url} className="px-5 py-3">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <SourceBadge value={c.platform} />
                        <span className="min-w-0 truncate text-sm font-medium text-zinc-100">{c.thread_title}</span>
                      </div>
                      <div className="num mt-1 truncate text-[11px] text-zinc-600">{c.url}</div>
                    </div>
                    <div className="flex shrink-0 items-center gap-3">
                      <span className="num text-xs text-zinc-400">relevance {score(c.relevance_score)}</span>
                      <button
                        className="btn-ghost !px-3 !py-1 text-xs"
                        onClick={() => toggle(id)}
                        aria-expanded={expanded}
                      >
                        {expanded ? "Hide comment" : "View comment"}
                      </button>
                    </div>
                  </div>
                  {expanded && (
                    <div className="mt-3 rounded-xl border border-accent/20 bg-accent/[0.05] px-4 py-3">
                      <div className="label mb-1.5">draft comment — posts only on your approval</div>
                      <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-zinc-300">{c.draft_comment}</p>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </Panel>

      <p className="text-xs text-zinc-600">
        The SEO &amp; Content agent drafts; you approve. Nothing is published, posted, or commented without an explicit
        approval.
      </p>
    </div>
  );
}
