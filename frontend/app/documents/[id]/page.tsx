"use client";

import { useParams } from "next/navigation";

import { DocumentDetailPage } from "@/components/procurement/detail-pages";

export default function Page() {
  const params = useParams<{ id: string }>();
  return <DocumentDetailPage id={params.id} />;
}
