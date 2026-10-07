"""Zero-Dependency Local HTTP Token Slashing Proxy.

Runs a lightweight loopback proxy that intercepts LLM completions,
compresses prompt payloads in flight, and forwards to upstream endpoints.
Zero external dependencies.
"""

from __future__ import annotations

import http.server
import socketserver
import urllib.request
import urllib.error
from typing import Optional

from apex_token_slasher.proxy.interceptor import TokenSlasherInterceptor


class SlasherProxyHandler(http.server.BaseHTTPRequestHandler):
    """HTTP request handler intercepting LLM payloads."""

    interceptor: TokenSlasherInterceptor = TokenSlasherInterceptor()
    upstream_base_url: str = "https://api.openai.com"

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        post_data = self.rfile.read(content_length)

        # Process and compress payload
        compressed_bytes, slashed = self.interceptor.process_openai_payload(post_data)

        # If offline or no upstream API key provided in request, return mock success response with savings
        auth_header = self.headers.get("Authorization", "")
        if not auth_header or "test" in auth_header.lower():
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Tokens-Initial", str(slashed.stats.initial_tokens))
            self.send_header("X-Tokens-Final", str(slashed.stats.final_tokens))
            self.send_header("X-Tokens-Saved", str(slashed.stats.tokens_saved))
            self.send_header("X-Savings-Ratio", f"{slashed.stats.savings_ratio:.2%}")
            self.send_header("X-Latency-Us", f"{slashed.stats.elapsed_microseconds:.1f}")
            self.end_headers()
            response_body = {
                "id": "slasher-mock-001",
                "object": "chat.completion",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": f"[APEX TOKEN SLASHER MOCK: Saved {slashed.stats.tokens_saved} tokens ({slashed.stats.savings_ratio:.1%}) in {slashed.stats.elapsed_microseconds:.1f}µs]"
                    },
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": slashed.stats.final_tokens,
                    "completion_tokens": 20,
                    "total_tokens": slashed.stats.final_tokens + 20
                }
            }
            import json
            self.wfile.write(json.dumps(response_body).encode("utf-8"))
            return

        # Forward to real upstream
        target_url = f"{self.upstream_base_url}{self.path}"
        req = urllib.request.Request(
            target_url,
            data=compressed_bytes,
            headers={k: v for k, v in self.headers.items() if k.lower() != "content-length"},
            method="POST",
        )
        req.add_header("Content-Length", str(len(compressed_bytes)))

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                self.send_response(resp.status)
                for header, val in resp.getheaders():
                    self.send_header(header, val)
                self.send_header("X-Tokens-Saved", str(slashed.stats.tokens_saved))
                self.end_headers()
                self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            self.send_response(502)
            self.end_headers()
            self.wfile.write(str(e).encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default HTTP server access logs."""
        pass


def run_slasher_proxy(port: int = 8080, upstream_url: str = "https://api.openai.com") -> None:
    """Starts the local token slashing proxy server."""
    SlasherProxyHandler.upstream_base_url = upstream_url
    with socketserver.TCPServer(("127.0.0.1", port), SlasherProxyHandler) as httpd:
        print(f"[*] Apex Token Slasher HTTP Proxy listening on http://127.0.0.1:{port}")
        print(f"[*] Upstream destination: {upstream_url}")
        print("[*] Transparent proxy ready. Press Ctrl+C to stop.")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[*] Proxy shutting down.")
