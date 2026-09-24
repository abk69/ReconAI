"use client";

import { useParams } from "next/navigation";

import { PolicyDetailPage } from "@/components/policies/policy-detail";

export default function Page() {
  const params = useParams<{ id: string }>();
  return <PolicyDetailPage id={params.id} />;
}
