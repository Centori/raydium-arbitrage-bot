/**
 * Custom type declarations to fix fetch-related type conflicts
 */

// Ensuring consistent Response type
interface Response {
  readonly headers: Headers;
  readonly ok: boolean;
  readonly redirected: boolean;
  readonly status: number;
  readonly statusText: string;
  readonly type: ResponseType;
  readonly url: string;
  clone(): Response;
  text(): Promise<string>;
  json(): Promise<any>;
  arrayBuffer(): Promise<ArrayBuffer>;
}

// Define consistent fetch function type
type FetchFn = (input: string | URL | Request, init?: RequestInit) => Promise<Response>;

declare module '@solana/web3.js' {
  // Augment the FetchMiddleware type to ensure it's compatible with our fetch types
  type FetchMiddleware = (
    url: string | URL | Request,
    options: RequestInit | undefined,
    callback: (newUrl: string | URL, newOptions: RequestInit) => void,
  ) => void;
}