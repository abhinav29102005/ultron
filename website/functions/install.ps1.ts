export async function onRequest(): Promise<Response> {
  const rawUrl = "https://raw.githubusercontent.com/abhinav29102005/ultron/main/scripts/install.ps1";
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
