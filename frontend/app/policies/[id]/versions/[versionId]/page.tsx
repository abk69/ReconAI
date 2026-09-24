"use client";

import { useParams } from "next/navigation";

import { PolicyVersionPage } from "@/components/policies/version-detail";

export default function Page() {
  const params = useParams<{ id: string; versionId: string }>();
  return <PolicyVersionPage policyId={params.id} versionId={params.versionId} />;
}
