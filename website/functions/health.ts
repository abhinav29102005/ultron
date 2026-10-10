export async function onRequest(): Promise<Response> {
  const data = {
    status: "healthy",
    agent: "ULTRON",
    service: "ultron-installer-gateway",
    version: "0.2.0",
    repository: "https://github.com/abhinav29102005/ultron",
    timestamp: new Date().toISOString(),
    endpoints: {
      installer_sh: "/install.sh",
      installer_ps1: "/install.ps1",
      installer_auto: "/install",
      keys_api: "/keys",
      health: "/health"
    }
  };

  return new Response(JSON.stringify(data, null, 2), {
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
      "Cache-Control": "no-cache, no-store, must-revalidate"
    }
  });
}
