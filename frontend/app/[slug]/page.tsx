import { notFound } from "next/navigation";

import { findNavItem, navigation } from "@/lib/navigation";

export function generateStaticParams() {
  return navigation
    .flatMap((section) => section.items)
    .filter((item) => !item.available)
    .map((item) => ({ slug: item.href.slice(1) }));
}

export default async function ComingSoonPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const href = `/${slug}`;
  const match = findNavItem(href);
  if (!match || match.item.available) {
    notFound();
  }
  const title = match.item.label;

  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="text-2xl font-semibold tracking-tight text-ink">{title}</h1>
      <p className="mt-3 text-sm leading-6 text-ink-muted">
        Coming in a later M10 milestone. This route is a placeholder so navigation stays stable.
        No data is loaded and no actions are available.
      </p>
    </div>
  );
}
