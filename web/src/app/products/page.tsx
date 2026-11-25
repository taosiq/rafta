import type { Metadata } from "next";
import { Suspense } from "react";

import { Skeleton } from "@/components/ui";
import { ProductsView } from "@/views/products-view";

export const metadata: Metadata = { title: "Products" };

export default function ProductsPage() {
  return (
    <Suspense fallback={<Skeleton className="h-[600px]" />}>
      <ProductsView />
    </Suspense>
  );
}
