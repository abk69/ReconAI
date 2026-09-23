"use client";

import { useParams } from "next/navigation";

import { InvoiceDetailPage } from "@/components/procurement/detail-pages";

export default function Page() {
  const params = useParams<{ id: string }>();
  return <InvoiceDetailPage id={params.id} />;
}
