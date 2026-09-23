"use client";

import { useParams } from "next/navigation";

import { ExceptionDetailPage } from "@/components/procurement/detail-pages";

export default function Page() {
  const params = useParams<{ id: string }>();
  return <ExceptionDetailPage id={params.id} />;
}
