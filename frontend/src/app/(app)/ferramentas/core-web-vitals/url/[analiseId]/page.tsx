import { CwvUrlClient } from "@/components/cwv/cwv-url-client";

export async function generateStaticParams() {
  return [{ analiseId: "placeholder" }];
}

export default function CwvUrlPage() {
  return <CwvUrlClient />;
}
