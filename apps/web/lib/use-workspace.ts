"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Organization } from "@/lib/types";

type User = { id: string; email: string; display_name: string };

export function useWorkspace() {
  const [authenticated, setAuthenticated] = useState(false);
  const [csrfToken, setCsrfToken] = useState("");
  const [organizationId, setOrganizationId] = useState("");
  const [user, setUser] = useState<User | null>(null);
  useEffect(() => {
    api<User>("/auth/me").then((value) => {
      const csrf = document.cookie.split("; ").find((row) => row.startsWith("csrf_token="))?.split("=")[1] ?? "";
      setCsrfToken(decodeURIComponent(csrf)); setUser(value); setAuthenticated(true);
    }).catch(() => undefined);
  }, []);
  const organizations = useQuery({
    queryKey: ["organizations"], queryFn: () => api<Organization[]>("/organizations"), enabled: authenticated,
  });
  useEffect(() => { if (!organizationId && organizations.data?.[0]) setOrganizationId(organizations.data[0].id); }, [organizations.data, organizationId]);
  return { authenticated, setAuthenticated, csrfToken, setCsrfToken, organizationId, setOrganizationId, organizations, user };
}
