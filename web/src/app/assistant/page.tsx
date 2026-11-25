"use client";

import clsx from "clsx";
import { ArrowUp, Bot, ChevronRight, Loader2, ShieldCheck, Wrench } from "lucide-react";
import Link from "next/link";
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";

import { Card, ErrorNote, PageHeader } from "@/components/ui";
import { api, type AssistantAnswer, type ToolCall } from "@/lib/api";
import { useApi } from "@/lib/hooks";

interface Status {
  mode: "llm" | "offline";
  model: string | null;
  tools: { name: string; description: string }[];
  examples: string[];
}

type Message = { role: "user"; text: string } | { role: "assistant"; answer: AssistantAnswer };

/** Minimal, safe renderer for the assistant's markdown subset: **bold**, `- ` bullets, *italic*. No HTML injection. */
function RichText({ text }: { text: string }) {
  const inline = (s: string): ReactNode[] =>
    s.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g).map((part, i) => {
      if (part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
      if (part.startsWith("*") && part.endsWith("*") && part.length > 2) return <em key={i}>{part.slice(1, -1)}</em>;
      return <Fragment key={i}>{part}</Fragment>;
    });
  const lines = text.split("\n");
  const out: ReactNode[] = [];
  let bullets: string[] = [];
  const flush = () => {
    if (bullets.length)
      out.push(
        <ul key={`ul${out.length}`} className="my-1 list-disc space-y-1 pl-5">
          {bullets.map((b, i) => (
            <li key={i}>{inline(b)}</li>
          ))}
        </ul>,
      );
    bullets = [];
  };
  lines.forEach((line, i) => {
    const m = line.match(/^\s*[-*]\s+(.*)$/);
    if (m) bullets.push(m[1]);
    else {
      flush();
      if (line.trim()) out.push(<p key={i}>{inline(line)}</p>);
    }
  });
  flush();
  return <div className="space-y-2 text-sm leading-6">{out}</div>;
}

function ToolTrace({ call }: { call: ToolCall }) {
  const [open, setOpen] = useState(false);
  const args = Object.entries(call.arguments)
    .filter(([, v]) => v !== null && v !== undefined)
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(", ");
  const products = (call.result as { products?: Record<string, unknown>[] }).products;
  return (
    <div className="rounded-md border border-border bg-bg text-xs">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-fg-2 hover:text-fg"
      >
        <ChevronRight size={12} className={clsx("transition-transform", open && "rotate-90")} />
        <Wrench size={12} aria-hidden />
        <code className="font-mono">
          {call.name}({args})
        </code>
        <span className="ml-auto text-muted">read-only</span>
      </button>
      {open && (
        <div className="border-t border-border px-3 py-2">
          {products && products.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr>
                    {Object.keys(products[0])
                      .slice(0, 8)
                      .map((k) => (
                        <th key={k} className="px-2 py-1 text-left font-medium whitespace-nowrap text-muted">
                          {k}
                        </th>
                      ))}
                  </tr>
                </thead>
                <tbody>
                  {products.map((p, i) => (
                    <tr key={i} className="border-t border-border">
                      {Object.entries(p)
                        .slice(0, 8)
                        .map(([k, v]) => (
                          <td key={k} className="num px-2 py-1 whitespace-nowrap">
                            {k === "sku" ? (
                              <Link href={`/products/${v}`} className="hover:underline">
                                {String(v)}
                              </Link>
                            ) : (
                              String(v ?? "–")
                            )}
                          </td>
                        ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <pre className="max-h-64 overflow-auto font-mono whitespace-pre-wrap text-fg-2">
              {JSON.stringify(call.result, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

export default function AssistantPage() {
  const { data: status } = useApi<Status>("/assistant/status");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Braces matter: newer browsers return a Promise from scrollIntoView, which React
    // would otherwise treat as the effect's cleanup function and crash on.
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, pending]);

  const ask = async (question: string) => {
    const q = question.trim();
    if (!q || pending) return;
    setInput("");
    setError(null);
    setMessages((m) => [...m, { role: "user", text: q }]);
    setPending(true);
    try {
      const answer = await api.post<AssistantAnswer>("/assistant/ask", { question: q });
      setMessages((m) => [...m, { role: "assistant", answer }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The assistant is unavailable");
    } finally {
      setPending(false);
    }
  };

  return (
    <>
      <PageHeader
        title="Assistant"
        description="Ask about stock, reorders, forecasts and the policy experiment. Answers come only from your data."
        actions={
          status && (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-border px-2.5 py-1 text-xs text-fg-2">
              <Bot size={12} aria-hidden />
              {status.mode === "llm" ? `LLM · ${status.model}` : "Offline mode (no API key)"}
            </span>
          )
        }
      />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-4">
        <Card className="flex min-h-[560px] flex-col xl:col-span-3" padded={false}>
          <div className="flex-1 space-y-6 overflow-y-auto p-5" aria-live="polite">
            {messages.length === 0 && (
              <div className="flex flex-col items-start gap-3">
                <p className="text-sm text-muted">Try one of these:</p>
                <div className="flex flex-wrap gap-2">
                  {status?.examples.map((ex) => (
                    <button
                      key={ex}
                      onClick={() => ask(ex)}
                      className="rounded-full border border-border-strong px-3 py-1.5 text-sm text-fg-2 hover:bg-surface-2 hover:text-fg"
                    >
                      {ex}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((m, i) =>
              m.role === "user" ? (
                <div key={i} className="flex justify-end">
                  <div className="max-w-[80%] rounded-lg bg-surface-2 px-3.5 py-2 text-sm">{m.text}</div>
                </div>
              ) : (
                <div key={i} className="flex gap-3">
                  <div className="grid size-7 shrink-0 place-items-center rounded-md bg-accent-soft text-accent">
                    <Bot size={14} aria-hidden />
                  </div>
                  <div className="min-w-0 flex-1 space-y-3">
                    <RichText text={m.answer.answer} />
                    {m.answer.tool_calls.map((c, j) => (
                      <ToolTrace key={j} call={c} />
                    ))}
                    <div className="num text-xs text-muted">
                      {m.answer.mode === "llm" ? "LLM" : "Offline"} · {m.answer.latency_ms} ms
                      {m.answer.fallback_reason && (
                        <span title={m.answer.fallback_reason}> · LLM unavailable, answered offline</span>
                      )}
                    </div>
                  </div>
                </div>
              ),
            )}
            {pending && (
              <div className="flex items-center gap-2 text-sm text-muted">
                <Loader2 size={14} className="animate-spin" /> Querying your data…
              </div>
            )}
            {error && <ErrorNote error={new Error(error)} />}
            <div ref={endRef} />
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              ask(input);
            }}
            className="flex items-center gap-2 border-t border-border p-3"
          >
            <label htmlFor="q" className="sr-only">
              Ask a question
            </label>
            <input
              id="q"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              maxLength={500}
              placeholder="Which products will run out next week?"
              className="h-10 flex-1 rounded-md border border-border-strong bg-bg px-3 text-sm placeholder:text-muted"
            />
            <button
              type="submit"
              disabled={!input.trim() || pending}
              aria-label="Send"
              className="grid size-10 place-items-center rounded-md bg-accent text-accent-fg disabled:opacity-40"
            >
              <ArrowUp size={16} />
            </button>
          </form>
        </Card>

        <div className="flex flex-col gap-6">
          <Card title="How it stays safe">
            <ul className="space-y-2 text-sm text-fg-2">
              {[
                "The model never writes SQL. It can only call the whitelisted tools below.",
                "Arguments are type-checked and range-limited before anything runs.",
                "Queries run on a read-only database role inside a READ ONLY transaction.",
                "Results are capped at 50 rows, and every question is audit-logged.",
              ].map((t) => (
                <li key={t} className="flex gap-2">
                  <ShieldCheck size={14} className="mt-1 shrink-0 text-healthy" aria-hidden />
                  {t}
                </li>
              ))}
            </ul>
          </Card>
          <Card title="Available tools" padded={false}>
            <ul className="divide-y divide-border">
              {status?.tools.map((t) => (
                <li key={t.name} className="px-5 py-2.5">
                  <code className="font-mono text-xs text-fg">{t.name}</code>
                  <p className="text-xs text-muted">{t.description}</p>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </div>
    </>
  );
}
