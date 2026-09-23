"use client";

import { useParams } from "next/navigation";

import { ExceptionCenterDetail } from "@/components/workflow/exception-center";

export default function Page() {
  const params = useParams<{ id: string }>();
  return <ExceptionCenterDetail id={params.id} />;
}
