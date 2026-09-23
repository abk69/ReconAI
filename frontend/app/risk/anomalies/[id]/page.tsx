"use client";

import { useParams } from "next/navigation";

import { AnomalyDetailPage } from "@/components/risk/anomaly-detail";

export default function Page() {
  const params = useParams<{ id: string }>();
  return <AnomalyDetailPage id={params.id} />;
}
