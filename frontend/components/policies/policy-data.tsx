export function PolicyData({ text }: { text: string }) {
  return (
    <blockquote className="max-h-64 overflow-auto border-l-2 border-line bg-canvas px-3 py-2 text-sm leading-6 whitespace-pre-wrap text-ink">
      <p className="mb-1 text-xs font-medium tracking-wide text-ink-muted uppercase">Policy data</p>
      {text}
    </blockquote>
  );
}
