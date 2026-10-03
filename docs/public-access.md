# Optional public access

Local deployment and public exposure are separate milestones. Start with loopback URLs; enable trusted-LAN access deliberately; add public routes only after application health and authentication work.

## Cloudflare Tunnel workflow

1. The owner supplies their own domain and Cloudflare account.
2. Create or select a tunnel through supported tools or the dashboard.
3. Store its credential privately; never embed it in Compose examples or Git.
4. Route a chosen hostname to the verified local application's HTTP endpoint or its configured reverse proxy.
5. Set the application's canonical URL, trusted proxy/origin configuration, and callback URLs.
6. Test login, uploads, WebSockets, redirects, logout, and native clients from outside the LAN.

Inside a container, `localhost` is that container—not the Windows host. Use a deliberately shared network/service name or the documented host endpoint, and validate reachability from the actual tunnel process.

Do not infer a route solely from a port number. For Coolify, dashboard, real-time, and terminal routes need the configured proxy path verified end-to-end; an HTTP 200 on the dashboard does not prove WebSocket functionality.

Choose readable per-app hostnames such as `notes.example.com`. Nested wildcard names require explicit DNS and certificate planning; a wildcard certificate for `*.example.com` does not cover `app.deploy.example.com`.

## Authentication and compatibility

Public application routes require application authentication and a reviewed exposure policy. Administration interfaces should remain private or receive additional access controls. Optional identity gateways must be tested against native clients, WebDAV, APIs, webhooks, and federation; an interactive browser-login wall is not compatible with every client.

Matrix TURN/media calls and other non-HTTP protocols need their own networking plan. Do not assume an HTTP tunnel publishes arbitrary UDP services. Tailscale is an optional private-access path, not mandatory infrastructure.

SMTP, GitHub OAuth, DNS modifications, port forwarding, and identity-provider setup require the owner's external account configuration. The installer must explain these steps and verify them without silently opening ports or publishing services.

Provider limits and upstream proxy requirements will be checked against official current documentation during the networking implementation phase. No public route is created by this release.
