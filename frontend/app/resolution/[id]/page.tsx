"use client";

import { useParams } from "next/navigation";

import { ResolutionDetail } from "@/components/workflow/resolution-detail";

export default function Page() {
  const params = useParams<{ id: string }>();
  return <ResolutionDetail id={params.id} />;
}
