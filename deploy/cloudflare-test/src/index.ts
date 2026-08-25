import {
  Container,
  ContainerProxy,
  getContainer,
} from "@cloudflare/containers";

interface Env {
  HONEYOS_CONTAINER: DurableObjectNamespace<HoneyOSContainer>;
  STATE_BUCKET: R2Bucket;
  API_SERVER_KEY: string;
  DEEPSEEK_API_KEY: string;
  BASIC_USERNAME: string;
  BASIC_PASSWORD: string;
  LOGIN_SESSION_TOKEN: string;
}

export class HoneyOSContainer extends Container<Env> {
  defaultPort = 8080;
  requiredPorts = [8080];
  sleepAfter = "168h";
  enableInternet = true;
  envVars = {
    HONEYOS_HOME: "/data",
    HONEYOS_ALLOW_REMOTE_COMPANION_UI: "1",
    API_SERVER_KEY: this.env.API_SERVER_KEY,
    DEEPSEEK_API_KEY: this.env.DEEPSEEK_API_KEY,
  };

}

HoneyOSContainer.outboundByHost = {
  "honeyos-state.r2": async (
    request: Request,
    env: Env,
    ctx: { containerId: string },
  ): Promise<Response> => {
    const path = new URL(request.url).pathname.replace(/^\/+/, "");
    const key = `${ctx.containerId}/${path || "state.tar.gz"}`;
    if (request.method === "PUT") {
      const body = await request.arrayBuffer();
      await env.STATE_BUCKET.put(key, body, {
        httpMetadata: { contentType: "application/octet-stream" },
      });
      return new Response(null, { status: 204 });
    }
    if (request.method === "GET") {
      const object = await env.STATE_BUCKET.get(key);
      if (!object) return new Response("not found", { status: 404 });
      return new Response(object.body, {
        headers: { "content-type": "application/octet-stream" },
      });
    }
    return new Response("method not allowed", { status: 405 });
  },
};

HoneyOSContainer.outbound = (request: Request): Promise<Response> => fetch(request);

export { ContainerProxy };

function hasValidSession(request: Request, env: Env): boolean {
  const cookie = request.headers.get("cookie") ?? "";
  return cookie
    .split(/;\s*/)
    .includes(`honeyos_pm_session=${env.LOGIN_SESSION_TOKEN}`);
}

function loginPage(invalid = false): Response {
  const error = invalid
    ? '<p class="error">用户名或密码不正确，请再试一次。</p>'
    : "";
  return new Response(
    `<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>登录 HoneyOS</title>
    <style>
      * { box-sizing: border-box; }
      body { margin: 0; min-height: 100vh; display: grid; place-items: center; padding: 24px; background: #f5f0e8; color: #28231f; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
      main { width: min(420px, 100%); padding: 40px; border: 1px solid #ded6ca; border-radius: 28px; background: rgba(255,255,255,.86); box-shadow: 0 24px 70px rgba(64,45,28,.12); }
      .mark { width: 52px; height: 52px; display: grid; place-items: center; border-radius: 18px; background: #2e2925; color: white; font-size: 24px; }
      h1 { margin: 26px 0 8px; font-size: 30px; letter-spacing: -.04em; }
      p { margin: 0 0 28px; color: #786f66; line-height: 1.6; }
      label { display: block; margin: 18px 0 8px; font-size: 14px; font-weight: 650; }
      input { width: 100%; height: 52px; padding: 0 16px; border: 1px solid #d9d0c5; border-radius: 15px; background: white; color: #28231f; font-size: 16px; outline: none; }
      input:focus { border-color: #b76a2b; box-shadow: 0 0 0 3px rgba(183,106,43,.13); }
      button { width: 100%; height: 52px; margin-top: 24px; border: 0; border-radius: 15px; background: #b86729; color: white; font-size: 16px; font-weight: 700; cursor: pointer; }
      button:hover { background: #a85c22; }
      .error { margin: 18px 0 0; color: #b53b30; font-size: 14px; }
    </style>
  </head>
  <body>
    <main>
      <div class="mark">H</div>
      <h1>进入 HoneyOS</h1>
      <p>这是仅供产品测试的私人空间。</p>
      <form method="post" action="/__login">
        <label for="username">用户名</label>
        <input id="username" name="username" autocomplete="username" required autofocus />
        <label for="password">密码</label>
        <input id="password" name="password" type="password" autocomplete="current-password" required />
        ${error}
        <button type="submit">进入</button>
      </form>
    </main>
  </body>
</html>`,
    {
      status: invalid ? 401 : 200,
      headers: {
        "content-type": "text/html; charset=UTF-8",
        "cache-control": "no-store",
      },
    },
  );
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const isPublicAsset =
      url.pathname.startsWith("/assets/") ||
      url.pathname === "/__bundle" ||
      url.pathname === "/__style" ||
      url.pathname === "/favicon.ico" ||
      url.pathname === "/manifest.webmanifest";
    if (url.pathname === "/__login" && request.method === "POST") {
      const form = await request.formData();
      const username = String(form.get("username") ?? "");
      const password = String(form.get("password") ?? "");
      if (username !== env.BASIC_USERNAME || password !== env.BASIC_PASSWORD) {
        return loginPage(true);
      }
      return new Response(null, {
        status: 303,
        headers: {
          location: "/",
          "set-cookie": `honeyos_pm_session=${env.LOGIN_SESSION_TOKEN}; Path=/; Secure; HttpOnly; SameSite=None; Max-Age=604800`,
          "cache-control": "no-store",
        },
      });
    }

    if (!isPublicAsset && !hasValidSession(request, env)) {
      if (url.pathname.startsWith("/api/")) {
        return Response.json({ error: "Authentication required" }, { status: 401 });
      }
      return loginPage();
    }

    if (url.pathname === "/__state_check") {
      const objects = await env.STATE_BUCKET.list({ limit: 100 });
      return Response.json({
        objects: objects.objects.map((object) => ({
          key: object.key,
          size: object.size,
          uploaded: object.uploaded.toISOString(),
        })),
      });
    }

    let upstreamRequest = request;
    if (url.pathname === "/__bundle" || url.pathname === "/__style") {
      const file = url.searchParams.get("file") ?? "";
      if (!/^[A-Za-z0-9._-]+$/.test(file)) {
        return new Response("invalid asset", { status: 400 });
      }
      const upstreamUrl = new URL(request.url);
      upstreamUrl.pathname = `/assets/${file}`;
      upstreamUrl.search = "";
      upstreamRequest = new Request(upstreamUrl, request);
    }

    const headers = new Headers(upstreamRequest.headers);
    headers.set("authorization", `Bearer ${env.API_SERVER_KEY}`);
    headers.set("x-forwarded-proto", "https");
    const forwardedCookies = (request.headers.get("cookie") ?? "")
      .split(/;\s*/)
      .filter((item) => item && !item.startsWith("honeyos_local="))
      .join("; ");
    if (forwardedCookies) {
      headers.set("cookie", forwardedCookies);
    } else {
      headers.delete("cookie");
    }
    const proxied = new Request(upstreamRequest, { headers });
    const response = await getContainer(
      env.HONEYOS_CONTAINER,
      "pm-single-tester",
    ).fetch(proxied);
    const responseHeaders = new Headers(response.headers);
    responseHeaders.delete("x-frame-options");
    const csp = responseHeaders.get("content-security-policy");
    if (csp) {
      responseHeaders.set(
        "content-security-policy",
        csp
          .replace(/frame-ancestors\s+[^;]+/, "frame-ancestors *")
          .replace("script-src 'self'", "script-src 'self' 'unsafe-inline'")
          .replace("style-src 'self'", "style-src 'self' 'unsafe-inline'"),
      );
    }
    const contentType = responseHeaders.get("content-type") ?? "";
    if (contentType.includes("text/html")) {
      let html = await response.text();
      const scriptMatch = html.match(
        /<script[^>]*src="(?:\.\/|\/)assets\/([A-Za-z0-9._-]+\.js)"[^>]*><\/script>/,
      );
      if (scriptMatch) {
        const bundleUrl = new URL(request.url);
        bundleUrl.pathname = `/assets/${scriptMatch[1]}`;
        bundleUrl.search = "";
        const bundleResponse = await getContainer(
          env.HONEYOS_CONTAINER,
          "pm-single-tester",
        ).fetch(new Request(bundleUrl, { headers }));
        if (bundleResponse.ok) {
          const bundle = (await bundleResponse.text()).replace(
            /<\/script/gi,
            "\\u003C/script",
          );
          html = html.replace(
            scriptMatch[0],
            () => `<script type="module">${bundle}</script>`,
          );
        }
      }
      const styleMatch = html.match(
        /<link[^>]*href="(?:\.\/|\/)assets\/([A-Za-z0-9._-]+\.css)"[^>]*>/,
      );
      if (styleMatch) {
        const styleUrl = new URL(request.url);
        styleUrl.pathname = `/assets/${styleMatch[1]}`;
        styleUrl.search = "";
        const styleResponse = await getContainer(
          env.HONEYOS_CONTAINER,
          "pm-single-tester",
        ).fetch(new Request(styleUrl, { headers }));
        if (styleResponse.ok) {
          const stylesheet = await styleResponse.text();
          html = html.replace(styleMatch[0], () => `<style>${stylesheet}</style>`);
        }
      }
      responseHeaders.delete("content-length");
      responseHeaders.delete("content-encoding");
      return new Response(html, {
        status: response.status,
        statusText: response.statusText,
        headers: responseHeaders,
      });
    }
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  },
};
