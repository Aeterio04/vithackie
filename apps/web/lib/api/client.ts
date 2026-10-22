import { z } from "zod";

export class ApiError extends Error {
  public readonly code: string;
  public readonly status: number;
  public readonly requestId?: string;
  public readonly details?: unknown;

  constructor(params: {
    message: string;
    code?: string;
    status: number;
    requestId?: string;
    details?: unknown;
  }) {
    super(params.message);
    this.name = "ApiError";
    this.code = params.code || `HTTP_${params.status}`;
    this.status = params.status;
    this.requestId = params.requestId;
    this.details = params.details;
  }
}

interface RequestOptions<TResponse> {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  headers?: Record<string, string>;
  schema?: z.ZodType<TResponse>;
  timeoutMs?: number;
  signal?: AbortSignal;
}

export async function apiClient<TResponse = unknown>(
  endpoint: string,
  options: RequestOptions<TResponse> = {}
): Promise<TResponse> {
  const {
    method = "GET",
    body,
    headers = {},
    schema,
    timeoutMs = 30000,
    signal: userSignal,
  } = options;

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  // Link user signal if provided
  if (userSignal) {
    userSignal.addEventListener("abort", () => controller.abort());
  }

  const reqHeaders: Record<string, string> = {
    Accept: "application/json",
    ...headers,
  };

  let serializedBody: BodyInit | undefined;
  if (body !== undefined) {
    if (body instanceof FormData) {
      serializedBody = body;
      // Let browser set multipart boundary
      delete reqHeaders["Content-Type"];
    } else {
      reqHeaders["Content-Type"] = "application/json";
      serializedBody = JSON.stringify(body);
    }
  }

  try {
    const res = await fetch(endpoint, {
      method,
      headers: reqHeaders,
      body: serializedBody,
      signal: controller.signal,
      credentials: "include", // send httpOnly cookies
    });

    clearTimeout(timeoutId);

    // Handle 401 Unauthorized
    if (res.status === 401) {
      if (typeof window !== "undefined") {
        const currentPath = window.location.pathname;
        if (!currentPath.startsWith("/login")) {
          const returnUrl = encodeURIComponent(
            window.location.pathname + window.location.search
          );
          window.location.href = `/login?returnUrl=${returnUrl}`;
        }
      }
      throw new ApiError({
        message: "Session expired or unauthorized. Please log in.",
        code: "UNAUTHORIZED",
        status: 401,
      });
    }

    const contentType = res.headers.get("content-type") || "";
    const isJson = contentType.includes("application/json");

    let responseData: unknown = null;
    if (isJson) {
      try {
        responseData = await res.json();
      } catch {
        responseData = null;
      }
    } else if (res.status !== 204) {
      responseData = await res.text();
    }

    if (!res.ok) {
      const errObj =
        typeof responseData === "object" && responseData !== null
          ? (responseData as Record<string, unknown>)
          : {};

      const message =
        (typeof errObj.message === "string" && errObj.message) ||
        (typeof errObj.detail === "string" && errObj.detail) ||
        res.statusText ||
        "Request failed";

      const code =
        (typeof errObj.code === "string" && errObj.code) || `HTTP_${res.status}`;
      const requestId =
        (typeof errObj.request_id === "string" && errObj.request_id) ||
        res.headers.get("x-request-id") ||
        undefined;

      throw new ApiError({
        message,
        code,
        status: res.status,
        requestId,
        details: errObj.details || responseData,
      });
    }

    if (!schema) {
      return responseData as TResponse;
    }

    const parseResult = schema.safeParse(responseData);
    if (!parseResult.success) {
      console.warn("Schema validation warning for:", endpoint, parseResult.error);
      // Fallback to responseData if schema fails in edge cases to avoid breaking UI
      return (responseData as TResponse) ?? ({} as TResponse);
    }

    return parseResult.data;
  } catch (err: unknown) {
    clearTimeout(timeoutId);

    if (err instanceof ApiError) {
      throw err;
    }

    if (err instanceof Error && err.name === "AbortError") {
      throw new ApiError({
        message: `Request timed out after ${timeoutMs}ms`,
        code: "TIMEOUT",
        status: 408,
      });
    }

    throw new ApiError({
      message: err instanceof Error ? err.message : "Network error",
      code: "NETWORK_ERROR",
      status: 0,
    });
  }
}

/**
 * Upload files via XMLHttpRequest with live progress reporting
 */
export function uploadWithProgress<TResponse = unknown>(params: {
  endpoint: string;
  formData: FormData;
  onProgress?: (percent: number, loaded: number, total: number) => void;
  schema?: z.ZodType<TResponse>;
}): Promise<TResponse> {
  const { endpoint, formData, onProgress, schema } = params;

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", endpoint);
    xhr.withCredentials = true;

    if (xhr.upload && onProgress) {
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          const percent = Math.round((event.loaded / event.total) * 100);
          onProgress(percent, event.loaded, event.total);
        }
      };
    }

    xhr.onload = () => {
      const status = xhr.status;
      if (status === 401) {
        if (typeof window !== "undefined") {
          window.location.href = `/login?returnUrl=${encodeURIComponent(
            window.location.pathname
          )}`;
        }
        return reject(
          new ApiError({
            message: "Unauthorized",
            code: "UNAUTHORIZED",
            status: 401,
          })
        );
      }

      let parsed: unknown;
      try {
        parsed = JSON.parse(xhr.responseText);
      } catch {
        parsed = xhr.responseText;
      }

      if (status >= 200 && status < 300) {
        if (schema) {
          const res = schema.safeParse(parsed);
          if (res.success) {
            return resolve(res.data);
          }
          console.warn("Upload schema validation warning:", res.error);
        }
        return resolve(parsed as TResponse);
      }

      const errObj =
        typeof parsed === "object" && parsed !== null
          ? (parsed as Record<string, unknown>)
          : {};
      return reject(
        new ApiError({
          message:
            (typeof errObj.message === "string" && errObj.message) ||
            xhr.statusText ||
            "Upload failed",
          code: (typeof errObj.code === "string" && errObj.code) || `HTTP_${status}`,
          status,
          details: parsed,
        })
      );
    };

    xhr.onerror = () => {
      reject(
        new ApiError({
          message: "Network error during upload",
          code: "NETWORK_ERROR",
          status: 0,
        })
      );
    };

    xhr.send(formData);
  });
}

apiClient.get = <TResponse = unknown>(
  endpoint: string,
  options?: Omit<RequestOptions<TResponse>, "method">
): Promise<TResponse> => {
  return apiClient<TResponse>(endpoint, { ...options, method: "GET" });
};

apiClient.post = <TResponse = unknown>(
  endpoint: string,
  body?: unknown,
  options?: Omit<RequestOptions<TResponse>, "method" | "body">
): Promise<TResponse> => {
  return apiClient<TResponse>(endpoint, { ...options, method: "POST", body });
};

apiClient.put = <TResponse = unknown>(
  endpoint: string,
  body?: unknown,
  options?: Omit<RequestOptions<TResponse>, "method" | "body">
): Promise<TResponse> => {
  return apiClient<TResponse>(endpoint, { ...options, method: "PUT", body });
};

apiClient.delete = <TResponse = unknown>(
  endpoint: string,
  options?: Omit<RequestOptions<TResponse>, "method">
): Promise<TResponse> => {
  return apiClient<TResponse>(endpoint, { ...options, method: "DELETE" });
};

