import { NextResponse, type NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Public paths that do not require auth check
  const isPublicPath =
    pathname.startsWith("/login") ||
    pathname.startsWith("/api") ||
    pathname.startsWith("/_next") ||
    pathname.includes(".") || // static assets e.g. favicon.ico
    pathname === "/favicon.ico";

  if (isPublicPath) {
    return NextResponse.next();
  }

  // Check for common auth cookies set by backend session
  const sessionCookie =
    request.cookies.get("session") ||
    request.cookies.get("access_token") ||
    request.cookies.get("auth_token") ||
    request.cookies.get("token") ||
    request.cookies.get("kawach_session");

  // Allow bypass in dev mock mode if configured
  const useMocks = process.env.NEXT_PUBLIC_USE_MOCKS === "true";

  if (!sessionCookie && !useMocks) {
    const returnUrl = encodeURIComponent(pathname + request.nextUrl.search);
    return NextResponse.redirect(new URL(`/login?returnUrl=${returnUrl}`, request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
