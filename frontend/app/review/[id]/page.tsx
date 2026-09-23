"use client";

import { useParams } from "next/navigation";

import { ReviewDetail } from "@/components/workflow/review-detail";

export default function Page() {
  const params = useParams<{ id: string }>();
  return <ReviewDetail id={params.id} />;
}
