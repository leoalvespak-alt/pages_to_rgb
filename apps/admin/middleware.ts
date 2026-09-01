import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(req: NextRequest) {
  const path = req.nextUrl.pathname;
  if (path.startsWith("/admin/login") || path.startsWith("/_next") || path.startsWith("/favicon")) {
    return NextResponse.next();
  }
  if (path.startsWith("/admin")) {
    const token = req.cookies.get("admin_session")?.value;
    if (!token) {
      return NextResponse.redirect(new URL("/admin/login", req.url));
    }
  }
  return NextResponse.next();
}
export const config = { matcher: ["/admin/:path*"] };
