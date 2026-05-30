import { LoaderIcon } from "lucide-react";

export default function Loading() {
  return (
    <div className="flex items-center justify-center py-16">
      <LoaderIcon className="size-6 text-muted-foreground animate-spin" />
    </div>
  );
}
