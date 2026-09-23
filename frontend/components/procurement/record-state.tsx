import type { ReactNode } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/ui/state";
import type { ResourceState } from "@/components/procurement/use-resource";

export function RecordState<T>({
  state,
  loadingTitle,
  empty,
  children,
}: {
  state: ResourceState<T>;
  loadingTitle: string;
  empty: { title: string; description: string } | null;
  children: (data: T) => ReactNode;
}) {
  if (state.kind === "loading") {
    return <LoadingState title={loadingTitle} description="Waiting for the API." />;
  }
  if (state.kind === "error") {
    return <ErrorState title="Request failed" description={state.message} />;
  }
  if (empty) {
    return <EmptyState title={empty.title} description={empty.description} />;
  }
  return children(state.data);
}
