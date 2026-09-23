import { ReconciliationPage } from "@/components/procurement/reconciliation-page";

export default function Page() {
  return (
    <ReconciliationPage
      detailBase="/exceptions"
      title="Exceptions"
      loadingTitle="Loading exceptions"
      description="Operational queue of persisted reconciliation exceptions. The engine identifies the fact. Human review and controlled resolution happen on the linked records. This page does not generate an AI explanation."
      emptyTitle="No exceptions match this filter"
      emptyDescription="No persisted exceptions match the current server-side filters."
    />
  );
}
