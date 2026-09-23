"use client";

import { useParams } from "next/navigation";

import { DocumentIntelligencePage } from "@/components/documents/document-detail";

export default function Page() {
  const params = useParams<{ id: string }>();
  return <DocumentIntelligencePage id={params.id} />;
}
