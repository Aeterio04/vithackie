import { NextResponse, type NextRequest } from "next/server";

/**
 * Route guard (Next 16 "proxy", formerly middleware). It only checks that a session cookie is PRESENT so signed-out
 * visitors are sent to /login quickly; the backend is what actually validates the JWT, and any 401 from the API
 * sends the user back to /login with a "session expired" notice. There is no bypass: no mock or demo mode.
 */
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;

  const isPublicPath =
    pathname.startsWith("/login") ||
    pathname.startsWith("/register") ||
    pathname.startsWith("/api") ||
    pathname.startsWith("/_next") ||
    pathname.includes(".") || // static assets e.g. favicon.ico
    pathname === "/favicon.ico";

  if (isPublicPath) {
    return NextResponse.next();
  }

  // httpOnly cookies set by the backend on login/register
  const sessionCookie =
    request.cookies.get("auth_token") ||
    request.cookies.get("access_token") ||
    request.cookies.get("token") ||
    request.cookies.get("session") ||
    request.cookies.get("kawach_session");

  if (!sessionCookie) {
    const returnUrl = pathname === "/" ? "/projects" : pathname + request.nextUrl.search;
    return NextResponse.redirect(new URL(`/login?returnUrl=${encodeURIComponent(returnUrl)}`, request.url));
  }

  if (pathname === "/") {
    return NextResponse.redirect(new URL("/projects", request.url));
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
