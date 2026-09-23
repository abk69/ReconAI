"use client";

import { useParams } from "next/navigation";

import { PurchaseOrderDetailPage } from "@/components/procurement/detail-pages";

export default function Page() {
  const params = useParams<{ id: string }>();
  return <PurchaseOrderDetailPage id={params.id} />;
}
