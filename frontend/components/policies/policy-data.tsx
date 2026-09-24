export function PolicyData({ text }: { text: string }) {
  return (
    <blockquote className="max-h-64 overflow-auto rounded-xl border border-line bg-canvas px-4 py-3 text-sm leading-6 whitespace-pre-wrap text-ink">
      <p className="mb-1 text-xs font-medium tracking-wide text-ink-muted uppercase">Policy data</p>
      {text}
    </blockquote>
  );
}
