import { redirect } from "next/navigation";
import { isAuthenticated } from "@/lib/session";
import SharedApplication from "./ui/shared-application";

export const dynamic = "force-dynamic";

export default async function Home() {
  if (!(await isAuthenticated())) redirect("/login");
  return <SharedApplication />;
}
