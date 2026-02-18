"use client";

import { useSession, signIn, signOut } from "next-auth/react";

export function AuthButton() {
  const { data: session, status } = useSession();

  if (status === "loading") {
    return <button className="text-xs text-muted-foreground" disabled>Checking auth…</button>;
  }

  if (!session) {
    return (
      <button
        onClick={() => signIn("google")}
        className="text-xs text-primary underline underline-offset-4"
      >
        Sign in with Google
      </button>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-muted-foreground">
        {session.user?.email ?? "Signed in"}
      </span>
      <button
        onClick={() => signOut()}
        className="text-xs text-primary underline underline-offset-4"
      >
        Sign out
      </button>
    </div>
  );
}

