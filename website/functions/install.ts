export async function onRequest(context: any): Promise<Response> {
  const request = context.request;
  const userAgent = (request.headers.get("User-Agent") || "").toLowerCase();
  const isPowerShell = userAgent.includes("powershell") || userAgent.includes("winhttp");

  const targetScript = isPowerShell ? "install.ps1" : "install.sh";
  const rawUrl = `https://raw.githubusercontent.com/abhinav29102005/ultron/main/scripts/${targetScript}`;

  try {
    const res = await fetch(rawUrl, {
      headers: { "User-Agent": "Ultron-Installer-Gateway/0.2.0" }
    });
    if (res.ok) {
      const text = await res.text();
      return new Response(text, {
        headers: {
          "Content-Type": "text/plain; charset=utf-8",
          "Cache-Control": "no-cache, no-store, must-revalidate",
          "Access-Control-Allow-Origin": "*"
        }
      });
    }
  } catch (err) {}

  return Response.redirect(rawUrl, 302);
}
