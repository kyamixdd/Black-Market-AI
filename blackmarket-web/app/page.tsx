import { redirect } from "next/navigation";
import { isAuthenticated } from "@/lib/session";
import Dashboard from "./ui/dashboard";
export const dynamic = "force-dynamic";
export default async function Home() {
  if (!(await isAuthenticated())) redirect("/login");
  return <Dashboard />;
}