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
  ACCESS_TOKEN: string;
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

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const suppliedToken = url.searchParams.get("access");
    if (suppliedToken && suppliedToken === env.ACCESS_TOKEN) {
      url.searchParams.delete("access");
      return new Response(null, {
        status: 302,
        headers: {
          location: `${url.pathname}${url.search}${url.hash}`,
          "set-cookie": `honeyos_pm_access=${env.ACCESS_TOKEN}; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=604800`,
          "cache-control": "no-store",
        },
      });
    }

    const cookie = request.headers.get("cookie") ?? "";
    if (!cookie.split(/;\s*/).includes(`honeyos_pm_access=${env.ACCESS_TOKEN}`)) {
      return new Response("Not found", {
        status: 404,
        headers: { "cache-control": "no-store" },
      });
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

    const headers = new Headers(request.headers);
    headers.set("authorization", `Bearer ${env.API_SERVER_KEY}`);
    headers.set("x-forwarded-proto", "https");
    const proxied = new Request(request, { headers });
    return getContainer(env.HONEYOS_CONTAINER, "pm-single-tester").fetch(proxied);
  },
};
