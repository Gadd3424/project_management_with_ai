const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api/v1";

export class ApiError extends Error {
  constructor(public status: number, message: string, public code?: string) { super(message); }
}

export async function api<T>(
  path: string,
  options: RequestInit & { organizationId?: string; csrfToken?: string } = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.organizationId) headers.set("X-Organization-ID", options.organizationId);
  if (options.csrfToken) headers.set("X-CSRF-Token", options.csrfToken);
  if (options.body && !(options.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`${API_URL}${path}`, { ...options, headers, credentials: "include" });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(
      response.status,
      body.error?.message ?? body.detail ?? body.title ?? "API request failed",
      body.error?.code,
    );
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}
