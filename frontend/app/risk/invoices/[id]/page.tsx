"use client";

import { useParams } from "next/navigation";

import { RiskDetailPage } from "@/components/risk/risk-detail";

export default function Page() {
  const params = useParams<{ id: string }>();
  return <RiskDetailPage entityType="INVOICE" id={params.id} />;
}
