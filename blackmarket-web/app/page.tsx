import { redirect } from "next/navigation";
import { isAuthenticated } from "@/lib/session";
import OriginalDashboard from "./ui/original-dashboard";

export const dynamic = "force-dynamic";

export default async function Home() {
  if (!(await isAuthenticated())) redirect("/login");
  return <OriginalDashboard />;
}
