import { Suspense } from "react";

import { Skeleton } from "@/components/ui";
import { ProductDetailView } from "@/views/product-detail-view";

export default function ProductPage() {
  return (
    <Suspense fallback={<Skeleton className="h-[600px]" />}>
      <ProductDetailView />
    </Suspense>
  );
}
