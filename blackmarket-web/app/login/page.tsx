import { redirect } from "next/navigation";
import { isAuthenticated } from "@/lib/session";
import Login from "./ui/login";
export const dynamic = "force-dynamic";
export default async function LoginPage() {
  if (await isAuthenticated()) redirect("/");
  return <Login />;
}