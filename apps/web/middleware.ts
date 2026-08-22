import { NextRequest, NextResponse } from "next/server";

export function middleware(request: NextRequest) {
  if (!request.cookies.get("access_token")) {
    return NextResponse.redirect(new URL("/?login=required", request.url));
  }
  return NextResponse.next();
}

export const config = { matcher: ["/admin/:path*"] };
