"use client";

import { useSession, signIn, signOut } from "next-auth/react";
import { LogIn, LogOut } from "lucide-react";

export function AuthButton() {
  const { data: session, status } = useSession();

  if (status === "loading") {
    return (
      <div className="h-8 w-24 rounded-full bg-secondary animate-pulse" />
    );
  }

  if (!session) {
    return (
      <button
        onClick={() => signIn("google")}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-full border border-border bg-card hover:bg-accent transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring"
      >
        <LogIn className="w-3 h-3" />
        Sign in
      </button>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-full bg-secondary text-xs">
        <div className="w-5 h-5 rounded-full bg-primary/20 flex items-center justify-center text-[10px] font-bold text-primary uppercase">
          {session.user?.email?.[0] ?? "U"}
        </div>
        <span className="text-secondary-foreground max-w-[160px] truncate">
          {session.user?.email ?? "Signed in"}
        </span>
      </div>
      <button
        onClick={() => signOut()}
        className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-full border border-border bg-card hover:bg-destructive/10 hover:text-destructive hover:border-destructive/30 transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-ring"
      >
        <LogOut className="w-3 h-3" />
        Sign out
      </button>
    </div>
  );
}
