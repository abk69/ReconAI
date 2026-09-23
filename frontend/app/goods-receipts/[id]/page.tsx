"use client";

import { useParams } from "next/navigation";

import { GoodsReceiptDetailPage } from "@/components/procurement/detail-pages";

export default function Page() {
  const params = useParams<{ id: string }>();
  return <GoodsReceiptDetailPage id={params.id} />;
}
